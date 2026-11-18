#!/usr/bin/env python3
"""
Lane Seven Apparel -> lane7-products.json (weekly, GitHub Actions).

Pulls every sellable Lane Seven style from their PromoStandards API and writes
it in the same shape the SanMar sync uses for products.json, so the browse
page, product page, calculator and checkout Worker price it exactly like any
SanMar garment (Austin, 2026-11-18): case_price x 1.5 + decoration, 2XL+
upcharges from Lane Seven's own size prices, same decoration methods and
minimums. The nightly sync merges this file into products.json.

Credentials come from the LANE7_ID / LANE7_PASSWORD GitHub Secrets.
Standard library only.
"""
import os, re, sys, json, time
import urllib.request, urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

L7_ID = os.environ.get("LANE7_ID", "").strip()
L7_PW = os.environ.get("LANE7_PASSWORD", "").strip()
OUT = os.environ.get("LANE7_OUT_FILE", "lane7-products.json")
WORKERS = 6

BASE = "https://promostandards.lanesevenapparel.com"
URL = {
    "product": BASE + "/productData.php",
    "pricing": BASE + "/productPricingAndConfig.php",
    "media":   BASE + "/mediaContent.php",
}
NS_PD = ('xmlns:ns="http://www.promostandards.org/WSDL/ProductDataService/2.0.0/" '
         'xmlns:shar="http://www.promostandards.org/WSDL/ProductDataService/2.0.0/SharedObjects/"')
NS_PPC = ('xmlns:ns="http://www.promostandards.org/WSDL/PricingAndConfiguration/1.0.0/" '
          'xmlns:shar="http://www.promostandards.org/WSDL/PricingAndConfiguration/1.0.0/SharedObjects/"')
NS_MED = ('xmlns:ns="http://www.promostandards.org/WSDL/MediaService/1.0.0/" '
          'xmlns:shar="http://www.promostandards.org/WSDL/MediaService/1.0.0/SharedObjects/"')

# Not garments we sell: damaged-goods lot, the printed catalog, face masks.
SKIP = {"ASST", "L7", "LSMASKS"}

SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL",
              "YXS", "YS", "YM", "YL", "YXL", "OSFA"]


# ---------------------------------------------------------------- SOAP helpers
def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def env(ns, op, body):
    return ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'{ns}><soapenv:Header/><soapenv:Body><ns:{op}>{body}</ns:{op}>'
            '</soapenv:Body></soapenv:Envelope>')


def creds():
    return f"<shar:id>{esc(L7_ID)}</shar:id><shar:password>{esc(L7_PW)}</shar:password>"


def post(url, action, xml, timeout=120):
    for attempt in range(3):
        r = urllib.request.Request(url, data=xml.encode("utf-8"), method="POST", headers={
            "Content-Type": "text/xml; charset=utf-8", "SOAPAction": action})
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code < 500 or attempt == 2:
                return body
        except Exception:
            if attempt == 2:
                return ""
        time.sleep(2 * (attempt + 1))
    return ""


def local(t):
    return t.rsplit("}", 1)[-1]


def parse(raw):
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        return None


def kids(root, name):
    return [e for e in root.iter() if local(e.tag) == name] if root is not None else []


def tx(root, name):
    if root is None:
        return ""
    for e in root.iter():
        if local(e.tag) == name and (e.text or "").strip():
            return e.text.strip()
    return ""


def direct(e, name):
    for c in e:
        if local(c.tag) == name and (c.text or "").strip():
            return c.text.strip()
    return ""


def get_sellable():
    return post(URL["product"], "getProductSellable", env(NS_PD, "GetProductSellableRequest",
        "<shar:wsVersion>2.0.0</shar:wsVersion>" + creds() +
        "<shar:localizationCountry>US</shar:localizationCountry>"
        "<shar:localizationLanguage>en</shar:localizationLanguage>"
        "<shar:isSellable>true</shar:isSellable>"), timeout=300)


def get_product(pid):
    return post(URL["product"], "getProduct", env(NS_PD, "GetProductRequest",
        "<shar:wsVersion>2.0.0</shar:wsVersion>" + creds() +
        "<shar:localizationCountry>US</shar:localizationCountry>"
        "<shar:localizationLanguage>en</shar:localizationLanguage>"
        f"<shar:productId>{esc(pid)}</shar:productId>"))


def get_fob(pid):
    return post(URL["pricing"], "getFobPoints", env(NS_PPC, "GetFobPointsRequest",
        "<shar:wsVersion>1.0.0</shar:wsVersion>" + creds() +
        f"<shar:productId>{esc(pid)}</shar:productId>"
        "<shar:localizationCountry>US</shar:localizationCountry>"
        "<shar:localizationLanguage>en</shar:localizationLanguage>"))


def get_price(pid, fob):
    return post(URL["pricing"], "getConfigurationAndPricing", env(NS_PPC, "GetConfigurationAndPricingRequest",
        "<shar:wsVersion>1.0.0</shar:wsVersion>" + creds() +
        f"<shar:productId>{esc(pid)}</shar:productId>"
        "<shar:currency>USD</shar:currency>"
        f"<shar:fobId>{esc(fob)}</shar:fobId>"
        "<shar:priceType>Net</shar:priceType>"
        "<shar:localizationCountry>US</shar:localizationCountry>"
        "<shar:localizationLanguage>en</shar:localizationLanguage>"
        "<shar:configurationType>Blank</shar:configurationType>"))


def get_media(pid):
    return post(URL["media"], "getMediaContent", env(NS_MED, "GetMediaContentRequest",
        "<shar:wsVersion>1.1.0</shar:wsVersion>" + creds() +
        "<shar:cultureName>en-US</shar:cultureName>"
        "<shar:mediaType>Image</shar:mediaType>"
        f"<shar:productId>{esc(pid)}</shar:productId>"))


# ---------------------------------------------------------------- mapping
def category_for(cat, name):
    """Lane Seven category / product name -> the site's catalog categories."""
    s = f"{cat} {name}".lower()
    if "youth" in s:
        return "Youth"
    if any(k in s for k in ("jogger", "pant", "short", "sweatpant")):
        return "Bottoms"
    if "polo" in s:
        return "Polos/Knits"
    if any(k in s for k in ("tee", "t-shirt", "tank", "long sleeve")) and "fleece" not in s:
        return "T-Shirts"
    if any(k in s for k in ("hood", "crew", "fleece", "sweat", "zip", "pullover", "quarter")):
        return "Sweatshirts/Fleece"
    if any(k in s for k in ("jacket", "vest", "coat")):
        return "Outerwear"
    return "Sweatshirts/Fleece"


def nice(s):
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s.title() if s.isupper() else s


def size_key(s):
    return (SIZE_ORDER.index(s) if s in SIZE_ORDER else 99, s)


VIEW = re.compile(r"^([A-Z]+)(\d)(front|side|back|frontw|sidew|backw|flat|flat2)_", re.I)
VIEW_SLOT = {"flat": "front_flat", "flat2": "back_flat", "front": "front_model",
             "back": "back_model", "side": "side_model",
             "frontw": "front_model_w", "backw": "back_model_w", "sidew": "side_model_w"}


def media_by_code(root, style):
    """{colorCode: {slot: url}} from Lane Seven image names like
    ls11001BK7flat_0820....png (style + color code + view number + view)."""
    out = {}
    pre = style.lower()
    for m in kids(root, "MediaContent"):
        url = direct(m, "url")
        cls = {(c.text or "").strip() for c in m.iter() if local(c.tag) == "classTypeName"}
        if not url or "High Resolution" in cls:
            continue
        name = url.rsplit("/", 1)[-1]
        if not name.lower().startswith(pre):
            continue
        mv = VIEW.match(name[len(pre):])
        if not mv:
            continue
        code, view = mv.group(1).upper(), mv.group(3).lower()
        slot = VIEW_SLOT.get(view)
        out.setdefault(code, {}).setdefault(slot, url)
    return out


def build(pid):
    log = []
    pr = parse(get_product(pid))
    prod = next(iter(kids(pr, "Product")), None)
    name = tx(prod, "productName")
    if not name:
        return None, [f"{pid}: GetProduct failed"]
    cat_raw = tx(prod, "category")

    # parts: partId -> (color, hex, size, weight)
    parts = {}
    for pp in kids(prod, "ProductPart"):
        part = direct(pp, "partId")
        if not part:
            continue
        if tx(pp, "isCloseout").lower() == "true":
            continue
        parts[part] = {"color": nice(tx(pp, "colorName")), "hex": tx(pp, "hex"),
                       "size": tx(pp, "labelSize").upper().replace("XXL", "2XL").replace("XXXL", "3XL"),
                       "weight": tx(pp, "weight")}
    if not parts:
        return None, [f"{pid}: no open (non-closeout) parts"]

    fobs = [direct(f, "fobId") for f in kids(parse(get_fob(pid)), "FobPoint")]
    fob = "CADC" if "CADC" in fobs else (fobs[0] if fobs else "CADC")
    prices = {}
    for p in kids(parse(get_price(pid, fob)), "Part"):
        part = direct(p, "partId")
        rows = []
        for pp in [e for e in p.iter() if local(e.tag) == "PartPrice"]:
            try:
                rows.append((int(float(tx(pp, "minQuantity") or 1)), float(tx(pp, "price"))))
            except ValueError:
                pass
        if part and rows:
            prices[part] = min(rows)[1]          # one break (qty 1) at Lane Seven
    if not prices:
        g = next(iter(kids(prod, "ProductPrice")), None)
        try:
            base = float(tx(g, "price"))
            prices = {k: base for k in parts}
            log.append(f"{pid}: pricing service empty, used the product's base price")
        except (TypeError, ValueError):
            return None, [f"{pid}: no price"]

    # base = most common price among XS-XL; anything above it is a size upcharge
    by_size = {}
    for part, info in parts.items():
        if part in prices:
            by_size.setdefault(info["size"], []).append(prices[part])
    if not by_size:
        return None, [f"{pid}: parts have no prices"]
    std = [max(v) for s, v in by_size.items() if s in ("XS", "S", "M", "L", "XL")] or \
          [max(v) for v in by_size.values()]
    base = min(std)
    upcharges = {}
    for s, v in by_size.items():
        d = round(max(v) - base, 2)
        if d > 0.004:
            upcharges[s] = d
    sizes = sorted(by_size, key=size_key)

    media = media_by_code(parse(get_media(pid)), pid)
    colors, seen = [], set()
    for part, info in sorted(parts.items()):
        cname = info["color"] or "Standard"
        if cname in seen:
            continue
        seen.add(cname)
        code = re.sub(r"\d+$", "", part[len(pid):]).upper() if part.upper().startswith(pid.upper()) else ""
        img = media.get(code, {})
        front = img.get("front_flat") or img.get("front_model")
        if not front:
            log.append(f"{pid} {cname}: no photo, color hidden")
            continue
        hx = info["hex"].lstrip("#")
        colors.append({
            "name": cname, "code": code or cname,
            "hex": ("#" + hx.upper()) if re.fullmatch(r"[0-9A-Fa-f]{6}", hx) else "#CCCCCC",
            "images": {"front_model": img.get("front_model"), "back_model": img.get("back_model"),
                       "front_flat": front, "back_flat": img.get("back_flat"),
                       "side_model": img.get("side_model")},
        })
    if not colors:
        return None, log + [f"{pid}: no color has photos, product hidden"]

    try:
        weight = round(float(next(i["weight"] for i in parts.values() if i["weight"])), 2)
    except (StopIteration, ValueError):
        weight = None
    desc = tx(prod, "description") or name
    points = [tx(m, "pointCopy") for m in kids(prod, "ProductMarketingPoint")]
    points = [p for p in points if p and p.lower() not in desc.lower()]
    return {
        "style": pid,
        "name": f"Lane Seven {name}. {pid}",
        "brand": "Lane Seven",
        "category": category_for(cat_raw, name),
        "subcategory": cat_raw,
        "description": " ".join([desc] + points),
        "case_price": round(base, 2),
        "case_sale_price": None, "sale_start_date": None, "sale_end_date": None,
        "msrp": None,
        "piece_weight_lbs": weight,
        "product_status": "Regular",
        "discontinued": False,
        "available_sizes": sizes,
        "size_upcharges": upcharges,
        "colors": colors,
        "source": "lane7",
    }, log


def main():
    if not (L7_ID and L7_PW):
        print("LANE7_ID / LANE7_PASSWORD missing")
        return 1
    sell = parse(get_sellable())
    ids = []
    for e in kids(sell, "productId"):
        v = (e.text or "").strip()
        if v and v not in ids and v not in SKIP:
            ids.append(v)
    if not ids:
        print("::error::Lane Seven returned no sellable styles - not overwriting " + OUT)
        return 1

    products, logs, failed = [], [], []
    with ThreadPoolExecutor(WORKERS) as ex:
        for pid, fut in zip(ids, [ex.submit(build, i) for i in ids]):
            try:
                res, log = fut.result()
            except Exception as e:
                res, log = None, [f"{pid}: {type(e).__name__}: {e}"]
            logs += log
            if res:
                products.append(res)
            else:
                failed.append(pid)

    if len(products) < 0.7 * len(ids):
        print(f"::error::Only {len(products)}/{len(ids)} styles built - not overwriting {OUT}")
        print("\n".join(logs))
        return 1

    doc = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "source": "Lane Seven PromoStandards", "product_count": len(products),
           "products": products}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)

    from collections import Counter
    cats = Counter(p["category"] for p in products)
    lines = ["# Lane Seven sync", "",
             f"- Styles: {len(ids)} sellable | built: {len(products)} | skipped: {', '.join(failed) or 'none'}",
             "- Categories: " + ", ".join(f"{k} {v}" for k, v in cats.most_common()), ""]
    if logs:
        lines += ["## Notes", ""] + [f"- {l}" for l in logs]
    lines += ["", "## Styles", "", "| Style | Name | Category | Lane Seven category | Colors | Sizes |",
              "|---|---|---|---|---|---|"]
    for p in products:
        lines.append(f"| {p['style']} | {p['name'][11:60]} | {p['category']} | {p['subcategory']} | "
                     f"{len(p['colors'])} | {p['available_sizes'][0]}-{p['available_sizes'][-1]} |")
    text = "\n".join(lines) + "\n"
    print(text)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        open(sp, "a", encoding="utf-8").write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
