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


def main():
    doc = json.load(open(CATALOG, encoding="utf-8"))
    products = doc.get("products", doc) if isinstance(doc, dict) else doc
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"t": NOW, "styles": {}}
    for vend, fn in (("sanmar", sanmar_stock), ("ss", ss_stock)):
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
