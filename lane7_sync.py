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
# Austin 2026-11-18: Lane Seven is sometimes bought through another distributor
# at a higher price, so every Lane Seven blank is priced 30% higher than the
# API price. Applied to case_price and the 2XL+ upcharges; the site then adds
# its usual x1.5 and decoration on top (so the blank shows at API x 1.3 x 1.5).
PRICE_UPLIFT = 1.30

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
    if re.search(r"\bwom[ae]n'?s?\b", s):
        return "Women's"
    if "polo collar" in s:          # a crewneck sweatshirt with a polo collar
        return "Sweatshirts/Fleece"
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


VIEW = re.compile(r"^([A-Z]+)(\d+)([a-z][a-z0-9]*)_", re.I)
MODEL_SLOT = {"front": "front_model", "back": "back_model", "side": "side_model",
              "frontw": "front_model_w", "backw": "back_model_w", "sidew": "side_model_w"}


def view_slot(view):
    """Lane Seven view word -> our slot. Flats are the blank, no-model shots."""
    v = view.lower()
    if "flat" in v:
        return "back_flat" if re.search(r"flat\d|back|bk", v) else "front_flat"
    return MODEL_SLOT.get(v, "other")


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
        code, seq, view = mv.group(1).upper(), int(mv.group(2)), mv.group(3).lower()
        d = out.setdefault(code, {})
        d.setdefault("_views", set()).add(view)
        if "flat" in view:
            # Lane Seven numbers its flats inconsistently (flat/flat2, flat1/flat2,
            # flat2/flat3, or a lone flat2): the lowest-numbered flat is the
            # front, the next one the back.
            n = re.search(r"flat(\d*)", view).group(1)
            d.setdefault("_flats", {}).setdefault((int(n or 0), seq), url)
        else:
            d.setdefault(view_slot(view), url)
    for d in out.values():
        flats = [u for _, u in sorted(d.pop("_flats", {}).items())]
        if flats:
            d["front_flat"] = flats[0]
        if len(flats) > 1:
            d["back_flat"] = flats[1]
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
    # Lane Seven's own California warehouse first, then any other FOB that prices it.
    order = (["CADC"] if "CADC" in fobs else []) + [f for f in fobs if f != "CADC"][:6] or ["CADC"]
    prices = {}
    for fob in order:
        for p in kids(parse(get_price(pid, fob)), "Part"):
            part = direct(p, "partId")
            rows = []
            for pp in [e for e in p.iter() if local(e.tag) == "PartPrice"]:
                try:
                    rows.append((int(float(tx(pp, "minQuantity") or 1)), float(tx(pp, "price"))))
                except ValueError:
                    pass
            if part and rows:
                prices[part] = round(min(rows)[1] * PRICE_UPLIFT, 2)   # one break (qty 1)
        if prices:
            if fob != "CADC":
                log.append(f"{pid}: priced from FOB {fob}")
            break
    if not prices:
        g = next(iter(kids(prod, "ProductPrice")), None)
        try:
            base = float(tx(g, "price"))
            prices = {k: round(base * PRICE_UPLIFT, 2) for k in parts}
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
        # Austin 2026-11-18: the Front and Back photos must be the blank flat
        # garment (no model). Model shots go in the photo row after them.
        front = img.get("front_flat")
        if not front:
            log.append(f"{pid} {cname}: no blank front photo, color hidden "
                       f"(views: {', '.join(sorted(img.get('_views', []))) or 'none'})")
            continue
        if not img.get("back_flat"):
            log.append(f"{pid} {cname}: no blank back photo "
                       f"(views: {', '.join(sorted(img.get('_views', [])))})")
        hx = info["hex"].lstrip("#")
        colors.append({
            "name": cname, "code": code or cname,
            "hex": ("#" + hx.upper()) if re.fullmatch(r"[0-9A-Fa-f]{6}", hx) else "#CCCCCC",
            "images": {"front_flat": front, "back_flat": img.get("back_flat"),
                       "front_model": img.get("front_model"), "back_model": None, "side_model": None,
                       "gallery": [u for u in (img.get("back_model"), img.get("side_model")) if u]},
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


# ---------------------------------------------------------------- photo cleanup
# Austin 2026-11-18: no grey background and no wasted space. Lane Seven's flat
# shots sit on a flat #F4F4F4 studio grey, 750x1084 with lots of empty frame.
# Each flat is flood-filled from the border to white, cropped to the garment
# (+4% margin) and saved as a JPG in media/lane7/, which the nightly sync
# publishes with the site. Files are named after Lane Seven's (they carry a
# timestamp), so a photo is only processed once.
MEDIA_DIR = os.environ.get("LANE7_MEDIA_DIR", "media/lane7")
MEDIA_URL = os.environ.get("LANE7_MEDIA_URL",
                           "https://aliveprintshop.github.io/PriceCalculator/media/lane7")


def clean_photo(url, dest):
    import io
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                 timeout=60).read()
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    a = np.asarray(im).astype(np.int16)
    rgb, alpha = a[..., :3], a[..., 3]
    h, w = alpha.shape
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    near = (np.abs(rgb - bg).max(axis=2) <= 4) | (alpha < 16)
    # only background that touches the frame edge (never grey inside the garment)
    lab, _ = ndimage.label(near)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bgmask = np.isin(lab, list(edge))
    out = rgb.copy()
    out[bgmask] = 255
    # soften the cut edge so it doesn't look jagged
    ring = ndimage.binary_dilation(bgmask, iterations=1) & ~bgmask
    out[ring] = (out[ring] * 0.6 + 255 * 0.4).astype(np.int16)
    ys, xs = np.where(~bgmask)
    if len(ys) < 0.01 * h * w:
        raise ValueError("garment not found")
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    py, px = int(0.04 * (y1 - y0)), int(0.04 * (x1 - x0))
    y0, y1, x0, x1 = max(0, y0 - py), min(h, y1 + py), max(0, x0 - px), min(w, x1 + px)
    Image.fromarray(out[y0:y1, x0:x1].astype("uint8"), "RGB").save(dest, "JPEG", quality=85,
                                                                   optimize=True, progressive=True)


def clean_photos(products, log):
    try:
        import numpy, PIL, scipy  # noqa: F401
    except ImportError:
        log.append("photo cleanup skipped: Pillow/numpy/scipy not installed")
        return
    os.makedirs(MEDIA_DIR, exist_ok=True)
    jobs = {}
    for p in products:
        for c in p["colors"]:
            for k in ("front_flat", "back_flat"):
                u = c["images"].get(k)
                if u and u.startswith("http") and "lanesevenapparel.com" in u:
                    name = re.sub(r"\.\w+$", "", u.rsplit("/", 1)[-1]) + ".jpg"
                    jobs[u] = name

    def run(item):
        u, name = item
        dest = os.path.join(MEDIA_DIR, name)
        if os.path.exists(dest):
            return u, name, None
        try:
            clean_photo(u, dest)
            return u, name, None
        except Exception as e:
            return u, None, f"{type(e).__name__}: {e}"
    done, failed = {}, 0
    with ThreadPoolExecutor(8) as ex:
        for u, name, err in ex.map(run, jobs.items()):
            if name:
                done[u] = f"{MEDIA_URL}/{name}"
            else:
                failed += 1
                log.append(f"photo cleanup failed, original kept: {u.rsplit('/', 1)[-1]} ({err})")
    for p in products:
        for c in p["colors"]:
            for k in ("front_flat", "back_flat"):
                u = c["images"].get(k)
                if u in done:
                    c["images"][k] = done[u]
    keep = set(n for n in jobs.values())
    for f in os.listdir(MEDIA_DIR):           # drop photos Lane Seven replaced
        if f not in keep:
            os.remove(os.path.join(MEDIA_DIR, f))
    log.append(f"photos: {len(done)} cleaned (white background, cropped), {failed} failed")


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

    clean_photos(products, logs)

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
