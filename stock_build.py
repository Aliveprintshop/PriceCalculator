#!/usr/bin/env python3
"""Supplier stock for the product page (Austin, 20 Nov 2026).

Writes one small file per style:  <out>/<STYLE>.json
    {"t": "2026-11-20T21:05Z", "v": "sanmar"|"ss", "c": {"<color name>": {"<size>": qty}}}
plus <out>/_meta.json with counts (no prices).

Sources
  SanMar  sanmar_dip.txt over SFTP (updated hourly by SanMar; quantity per
          warehouse, capped by SanMar). Joined to products.json by the colour's
          INVENTORY_KEY ("ikey", written by sync-sanmar.py) and, for colours
          without one yet, by catalog colour name.
  S&S     /v2/products/ for the brands we carry (qty = all warehouses).

Run from the Pages publish (hourly) and the nightly sync, AFTER products.json
is final. Any failure leaves that vendor out; the page then shows no stock
line for those styles instead of a wrong one.

Env: SANMAR_FTP_USER / SANMAR_FTP_PASSWORD (+ optional HOST/PORT),
     SS_ACCOUNT / SS_API_KEY.
Usage: python stock_build.py products.json _site/stock
"""
import base64, collections, csv, io, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CATALOG = sys.argv[1] if len(sys.argv) > 1 else "products.json"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "_site/stock")
NOW = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime())
DIP_PATHS = ["sanmar_dip.txt", "SanMarPDD/sanmar_dip.txt", "Sanmar_dip.txt", "SanMarPDD/Sanmar_dip.txt",
             "SanMarDIP/sanmar_dip.txt"]


def log(m):
    print(m, flush=True)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def norm_size(s):
    s = (s or "").strip().upper()
    return {"X-SMALL": "XS", "SMALL": "S", "MEDIUM": "M", "LARGE": "L", "X-LARGE": "XL",
            "XX-LARGE": "2XL", "XXX-LARGE": "3XL", "XXXX-LARGE": "4XL", "XXXXX-LARGE": "5XL"}.get(s, s)


def safe_key(style):
    return re.sub(r"[^A-Z0-9_-]", "_", str(style).upper())


# ------------------------------------------------------------------ SanMar
def sanmar_stock(products):
    user, pw = os.environ.get("SANMAR_FTP_USER"), os.environ.get("SANMAR_FTP_PASSWORD")
    if not user or not pw:
        log("::warning::SanMar FTP secrets missing - no SanMar stock")
        return {}
    import paramiko
    host = os.environ.get("SANMAR_FTP_HOST", "ftp.sanmar.com")
    port = int(os.environ.get("SANMAR_FTP_PORT", "2200"))
    t = paramiko.Transport((host, port))
    t.connect(username=user, password=pw)
    sftp = paramiko.SFTPClient.from_transport(t)
    local = Path("/tmp/sanmar_dip.txt")
    got = None
    for p in DIP_PATHS:
        try:
            sftp.get(p, str(local)); got = p; break
        except IOError:
            continue
    if not got:
        for d in (".", "SanMarPDD"):
            try:
                log(f"  {d}: " + ", ".join(sorted(sftp.listdir(d))[:60]))
            except IOError:
                pass
        sftp.close(); t.close()
        log("::warning::sanmar_dip.txt not found - no SanMar stock")
        return {}
    sftp.close(); t.close()
    log(f"  SanMar: downloaded {got} ({local.stat().st_size // 1024} KB)")

    # products.json side: inventory key -> (style, colour name); style+colour name fallback
    by_ikey, by_name, styles = {}, {}, set()
    for p in products:
        if p.get("source") not in (None, "", "sanmar"):
            continue
        st = str(p.get("style"))
        styles.add(st.upper())
        for c in p.get("colors") or []:
            if c.get("ikey"):
                by_ikey[str(c["ikey"]).strip()] = (st, c["name"])
            by_name[(st.upper(), norm(c.get("name")))] = (st, c["name"])

    out = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(int)))
    rows = hit = 0
    with open(local, encoding="latin-1", newline="") as f:
        rd = csv.reader(f, delimiter="|", quotechar='"')
        first = next(rd, None)
        idx = {"ikey": 0, "style": 2, "color": 3, "size": 4, "qty": 6}
        if first and any("CATALOG" in (x or "").upper() for x in first):
            h = [re.sub(r"[\s#]+", "", (x or "").upper()) for x in first]
            def find(*names):
                for n in names:
                    if n in h:
                        return h.index(n)
                return None
            idx = {"ikey": find("INVENTORY_KEY", "INVENTORYKEY"), "style": find("CATALOG_NO", "CATALOGNO"),
                   "color": find("CATALOG_COLOR", "CATALOGCOLOR"), "size": find("SIZE"),
                   "qty": find("QUANTITY", "QTY")}
            first = None
        for row in (_chain(first, rd) if first else rd):
            rows += 1
            try:
                ik = row[idx["ikey"]].strip() if idx["ikey"] is not None else ""
                st = row[idx["style"]].strip()
                q = int(float(row[idx["qty"]] or 0))
                sz = norm_size(row[idx["size"]])
                col = row[idx["color"]].strip()
            except (IndexError, ValueError, TypeError):
                continue
            m = by_ikey.get(ik) or by_name.get((st.upper(), norm(col)))
            if not m:
                continue
            hit += 1
            out[m[0]][m[1]][sz] += max(0, q)
    log(f"  SanMar: {rows} stock rows, {hit} matched, {len(out)} styles")
    return out


def _chain(first, rd):
    yield first
    for r in rd:
        yield r


# ------------------------------------------------------------------ S&S
def ss_stock(products):
    acct, key = os.environ.get("SS_ACCOUNT", "").strip(), os.environ.get("SS_API_KEY", "").strip()
    if not acct or not key:
        log("::warning::S&S secrets missing - no S&S stock")
        return {}
    auth = "Basic " + base64.b64encode(f"{acct}:{key}".encode()).decode()

    def get(path, params=None):
        url = "https://api.ssactivewear.com/v2" + path + ("?" + urllib.parse.urlencode(params, safe=",") if params else "")
        for i in range(4):
            req = urllib.request.Request(url, headers={"Authorization": auth, "Accept": "application/json",
                                                       "User-Agent": "AlivePrintShop-stock"})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    left = r.headers.get("X-Rate-Limit-Remaining")
                    if left and left.isdigit() and int(left) < 5:
                        time.sleep(30)
                    return json.loads(r.read().decode("utf-8") or "[]")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return []
                if e.code in (429, 500, 502, 503, 504) and i < 3:
                    time.sleep(15 * (i + 1)); continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if i < 3:
                    time.sleep(10 * (i + 1)); continue
                raise

    ours = {}
    for p in products:
        if p.get("source") == "ss":
            ours[(norm(p.get("brand")), norm(p.get("vendor_style") or p.get("style")))] = str(p["style"])
    if not ours:
        return {}
    brands = {b for b, _ in ours}
    styles = [s for s in get("/styles/") if norm(s.get("brandName")) in brands
              and (norm(s.get("brandName")), norm(s.get("styleName"))) in ours]
    one = {"ADJUSTABLE", "ONE SIZE", "OSFA", "OS", "ONE SIZE FITS MOST", "OSFM"}
    out = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(int)))
    ids = [str(s["styleID"]) for s in styles]
    sid = {s["styleID"]: ours[(norm(s.get("brandName")), norm(s.get("styleName")))] for s in styles}
    n = 0
    for i in range(0, len(ids), 20):
        for k in get("/products/", {"styleid": ",".join(ids[i:i + 20])}):
            st = sid.get(k.get("styleID"))
            if not st:
                continue
            q = k.get("qty")
            if q is None:
                q = sum(int(w.get("qty") or 0) for w in (k.get("warehouses") or []))
            sz = re.sub(r"\s+", " ", str(k.get("sizeName") or "").strip()).upper()
            sz = "OSFA" if sz in one else {"XXL": "2XL", "XXXL": "3XL", "2X": "2XL", "3X": "3XL"}.get(sz, sz)
            out[st][k.get("colorName") or "Standard"][sz] += max(0, int(q or 0))
            n += 1
    log(f"  S&S: {len(styles)} styles, {n} SKUs")
    return out


# ------------------------------------------------------------------ PromoStandards (Lane Seven, PCNA)
def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _soap(url, xml, action="getInventoryLevels"):
    for i in range(3):
        req = urllib.request.Request(url, data=xml.encode(), method="POST",
                                     headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": action})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code < 500 or i == 2:
                return e.read().decode("utf-8", "replace")
        except Exception:
            if i == 2:
                return ""
        time.sleep(3 * (i + 1))
    return ""


def _xml(raw):
    import xml.etree.ElementTree as ET
    try:
        return ET.fromstring(raw)
    except Exception:
        return None


def _L(t):
    return t.rsplit("}", 1)[-1]


def _txt(e, name):
    for c in e.iter():
        if _L(c.tag) == name and c.text and c.text.strip():
            return c.text.strip()
    return ""


def _pool(fn, items, workers=4):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def lane7_stock(products):
    """Lane Seven Inventory 1.2.1: per style, quantity by colour code + size."""
    uid, pw = os.environ.get("LANE7_ID", "").strip(), os.environ.get("LANE7_PASSWORD", "").strip()
    if not uid or not pw:
        log("::warning::Lane Seven secrets missing - no Lane Seven stock")
        return {}
    url = "https://promostandards.lanesevenapparel.com/inventory.php"
    ns = "http://www.promostandards.org/WSDL/InventoryService/1.0.0/"
    mine = [p for p in products if p.get("source") == "lane7"]

    def one(p):
        st = str(p["style"])
        x = (f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns="{ns}">'
             f'<soapenv:Header/><soapenv:Body><ns:Request><ns:wsVersion>1.2.1</ns:wsVersion>'
             f'<ns:id>{_esc(uid)}</ns:id><ns:password>{_esc(pw)}</ns:password>'
             f'<ns:productID>{_esc(p.get("vendor_style") or st)}</ns:productID><ns:productIDtype>Supplier</ns:productIDtype>'
             f'</ns:Request></soapenv:Body></soapenv:Envelope>')
        root = _xml(_soap(url, x))
        if root is None:
            return st, None
        code2name = {str(c.get("code") or "").upper(): c["name"] for c in p.get("colors") or []}
        out = collections.defaultdict(dict)
        for v in root.iter():
            if _L(v.tag) != "ProductVariationInventory":
                continue
            col = code2name.get(_txt(v, "attributeColor").upper())
            if not col:
                continue
            sz = norm_size(_txt(v, "attributeSize"))
            sz = {"XXL": "2XL", "XXXL": "3XL"}.get(sz, sz)
            try:
                q = int(float(_txt(v, "quantityAvailable") or 0))
            except ValueError:
                continue
            out[col][sz] = out[col].get(sz, 0) + max(0, q)
        return st, out or None

    res = {st: d for st, d in _pool(one, mine) if d}
    log(f"  Lane Seven: {len(res)}/{len(mine)} styles")
    return res


def pcna_stock(products):
    """PCNA Inventory 2.0.0: quantity per part (colour). One-size items keyed by their one size."""
    uid, pw = os.environ.get("PCNA_ID", "").strip(), os.environ.get("PCNA_PASSWORD", "").strip()
    if not uid or not pw:
        log("::warning::PCNA secrets missing - no PCNA stock")
        return {}
    url = "https://psinventory200.pcna.online"
    ns = ('xmlns:ns="http://www.promostandards.org/WSDL/Inventory/2.0.0/" '
          'xmlns:shar="http://www.promostandards.org/WSDL/Inventory/2.0.0/SharedObjects/"')
    mine = [p for p in products if p.get("source") == "pcna"]
    ids = sorted({str(p.get("_pcnaId") or p["style"]) for p in mine})

    def one(pid):
        x = (f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" {ns}><soapenv:Header/>'
             f'<soapenv:Body><ns:GetInventoryLevelsRequest><shar:wsVersion>2.0.0</shar:wsVersion>'
             f'<shar:id>{_esc(uid)}</shar:id><shar:password>{_esc(pw)}</shar:password>'
             f'<shar:productId>{_esc(pid)}</shar:productId></ns:GetInventoryLevelsRequest></soapenv:Body></soapenv:Envelope>')
        root = _xml(_soap(url, x))
        parts = {}
        if root is not None:
            for v in root.iter():
                if _L(v.tag) != "PartInventory":
                    continue
                part = _txt(v, "partId")
                qa = [c for c in v if _L(c.tag) == "quantityAvailable"]
                try:
                    q = int(float(_txt(qa[0], "value"))) if qa else 0
                except ValueError:
                    q = 0
                parts[part.upper()] = (max(0, q), _txt(v, "partColor"))
        return pid, parts

    by_id = dict(_pool(one, ids))
    res = {}
    for p in mine:
        parts = by_id.get(str(p.get("_pcnaId") or p["style"])) or {}
        if not parts:
            continue
        key = (p.get("available_sizes") or ["Qty"])[0] or "Qty"
        cols = {}
        for c in p.get("colors") or []:
            hit = parts.get(str(c.get("sku") or "").upper())
            if hit is None:
                for q, pc in parts.values():
                    if norm(re.sub(r"\(.*\)", "", pc)) == norm(c["name"]):
                        hit = (q, pc); break
            if hit is not None:
                cols[c["name"]] = {key: hit[0]}
        if cols:
            res[str(p["style"])] = cols
    log(f"  PCNA: {len(ids)} products asked, {len(res)}/{len(mine)} styles with stock")
    return res


def main():
    doc = json.load(open(CATALOG, encoding="utf-8"))
    products = doc.get("products", doc) if isinstance(doc, dict) else doc
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"t": NOW, "styles": {}}
    for vend, fn in (("sanmar", sanmar_stock), ("ss", ss_stock), ("lane7", lane7_stock), ("pcna", pcna_stock)):
        try:
            data = fn(products)
        except Exception as e:
            log(f"::warning::{vend} stock failed: {e}")
            data = {}
        for st, cols in data.items():
            with open(OUT / (safe_key(st) + ".json"), "w") as f:
                json.dump({"t": NOW, "v": vend, "c": {c: dict(s) for c, s in cols.items()}}, f, separators=(",", ":"))
        meta["styles"][vend] = len(data)
    json.dump(meta, open(OUT / "_meta.json", "w"))
    log(f"stock: {meta}")


if __name__ == "__main__":
    main()
