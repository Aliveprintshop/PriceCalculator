#!/usr/bin/env python3
"""
S&S Activewear -> ss-products.json (weekly, GitHub Actions).

Starts with three brands (Austin, 2026-11-20): Imperial, Independent Trading
Co. and Valucap. Every current style of those brands is written in the same
shape the SanMar sync uses for products.json, and priced exactly like a SanMar
garment: the S&S account price is case_price, the site charges case_price x 1.5
plus decoration, and 2XL+ upcharges come from S&S's own per-size prices. The
nightly sync merges this file into products.json (merge-pcna.py).

No duplicates. S&S also carries many brands the site already sells. A style
whose brand AND style number are already on the site (from SanMar, Lane Seven,
PCNA...) is skipped: the existing product always wins. A style number that is
taken by a DIFFERENT brand's product (Imperial 6014 beanie vs Comfort Colors
6014 tee) is not a duplicate: it is added under a brand prefix, e.g. IMP-6014.

Photos (Austin, 2026-11-20, same rule as Lane Seven): Front and Back are the
blank flat garment; model shots go in the photo row. S&S flats are already on
white, so nothing is re-hosted; each flat gets a measured crop box, like
SanMar's. A colour with no flat front photo is hidden.

Credentials: SS_ACCOUNT / SS_API_KEY GitHub Secrets (Basic auth).
Standard library, plus Pillow + numpy for the crop boxes (skipped without them).
"""
import base64, collections, html, json, os, re, sys, time
import urllib.error, urllib.parse, urllib.request

ACCT = os.environ.get("SS_ACCOUNT", "").strip()
KEY = os.environ.get("SS_API_KEY", "").strip()
OUT = os.environ.get("SS_OUT_FILE", "ss-products.json")
CATALOG = os.environ.get("SS_CATALOG", "products.json")
BASE = "https://api.ssactivewear.com/v2"
IMG = "https://cdn.ssactivewear.com/"

# S&S brand name -> prefix used only when a style number is already taken by
# another brand's product on the site.
BRANDS = {"Imperial": "IMP", "Independent Trading Co.": "ITC", "Valucap": "VC"}

SIZE_ORDER = ["2T", "3T", "4T", "5T", "5/6", "5/6T", "XXS", "XS", "S", "M", "L", "XL",
              "2XL", "3XL", "4XL", "5XL", "6XL", "OSFA"]
ONE_SIZE = {"ADJUSTABLE", "ONE SIZE", "ADJ", "OS", "OSFA", "ONE SIZE FITS ALL"}

LOG = []
PREMIUMS = []   # (brand, style, premium colours, colours, max % above usual)
PREMIUM = os.environ.get("SS_PREMIUM", "price").strip().lower()


def log(s):
    LOG.append(s)


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


# ---------------------------------------------------------------- API
AUTH = "Basic " + base64.b64encode(f"{ACCT}:{KEY}".encode()).decode()


def get(path, params=None, tries=4):
    url = BASE + path + ("?" + urllib.parse.urlencode(params, safe=",") if params else "")
    for i in range(tries):
        req = urllib.request.Request(url, headers={"Authorization": AUTH, "Accept": "application/json",
                                                   "User-Agent": "AlivePrintShop-catalog-sync"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                left = r.headers.get("X-Rate-Limit-Remaining")
                if left and left.isdigit() and int(left) < 5:
                    time.sleep(30)          # S&S allows 60 requests a minute
                return json.loads(r.read().decode("utf-8") or "[]")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []                   # S&S answers 404 for "nothing matched"
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(15 * (i + 1))
                continue
            raise RuntimeError(f"HTTP {e.code} on {path}")
        except (urllib.error.URLError, TimeoutError):
            if i < tries - 1:
                time.sleep(10 * (i + 1))
                continue
            raise


# ---------------------------------------------------------------- mapping
def category_for(base_cat, title):
    """S&S baseCategory + title -> the site's catalog categories."""
    t, c = (title or "").lower(), (base_cat or "").lower()
    if "headwear" in c:
        return "Caps"
    if "bag" in c:
        return "Bags"
    if "accessor" in c:
        return "Accessories"
    if "toddler" in t or "infant" in t:
        return "Infant & Toddler"
    if re.search(r"\bwom[ae]n['’]?s?\b", t):
        return "Women's"
    if "youth" in t:
        return "Youth"
    if "bottom" in c or any(k in t for k in ("pant", "short", "jogger")):
        return "Bottoms"
    if "woven" in c or "flannel" in t:
        return "Woven Shirts"
    if "t-shirt" in c:
        return "T-Shirts"
    if "fleece" in c:
        return "Sweatshirts/Fleece"
    if "outerwear" in c or "knits & layering" in c or any(k in t for k in ("jacket", "vest", "anorak")):
        return "Outerwear"
    return "Sweatshirts/Fleece"


def size_name(s):
    s = re.sub(r"\s+", " ", str(s or "").strip())
    u = s.upper()
    if u in ONE_SIZE:
        return "OSFA"
    return {"XXL": "2XL", "XXXL": "3XL", "2X": "2XL", "3X": "3XL"}.get(u, u)


def size_key(s):
    return (SIZE_ORDER.index(s) if s in SIZE_ORDER else 50, s)


def img(path, large=True):
    if not path:
        return None
    p = str(path).lstrip("/")
    if large:
        p = re.sub(r"_fm(\.\w+)$", r"_fl\1", p)
    return p if p.startswith("http") else IMG + p


def clean_desc(raw):
    s = re.sub(r"(?i)<li[^>]*>", " ", raw or "")
    s = re.sub(r"(?i)</li>", ". ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s*\.\s*\.", ".", re.sub(r"\s+", " ", s)).strip()
    return s


def price_of(k):
    """The S&S account price for one SKU (customerPrice), else the case price."""
    for f in ("customerPrice", "casePrice", "piecePrice"):
        try:
            v = float(k.get(f) or 0)
        except (TypeError, ValueError):
            v = 0
        if v > 0:
            return v
    return 0.0


# ---------------------------------------------------------------- crops
def _runs(mask, gap):
    idx = [i for i, v in enumerate(mask) if v]
    if not idx:
        return None
    best, s, p = None, idx[0], idx[0]
    for i in idx[1:]:
        if i - p > gap:
            if best is None or p - s > best[1] - best[0]:
                best = (s, p)
            s = i
        p = i
    if best is None or p - s > best[1] - best[0]:
        best = (s, p)
    return best


def measure_crop(url):
    """Box around the product on a white photo: [x0,y0,x1,y1 per-mille, w/h*1000].
    Same method as sync-sanmar.py, so the page crops S&S flats like SanMar's."""
    import io
    import numpy as np
    from PIL import Image
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                 timeout=30).read()
    im = Image.open(io.BytesIO(raw))
    W, H = im.size
    im.draft("L", (W // 3, H // 3))
    g = np.asarray(im.convert("L")).astype(int)
    h, w = g.shape
    bg = np.median(np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]]))
    m = (g < 238) | (abs(g - bg) > 14)
    r = _runs(m.sum(axis=1) >= max(2, 0.008 * w), int(0.03 * h))
    if not r:
        return None
    y0, y1 = r
    c = _runs(m[y0:y1 + 1].sum(axis=0) >= max(2, 0.004 * (y1 - y0 + 1)), int(0.03 * w))
    if not c:
        return None
    x0, x1 = c
    box = [x0 / w, y0 / h, (x1 + 1) / w, (y1 + 1) / h]
    bw, bh, pad = box[2] - box[0], box[3] - box[1], 0.03
    box = [max(0, box[0] - pad * bw), max(0, box[1] - pad * bh), min(1, box[2] + pad * bw), min(1, box[3] + pad * bh)]
    return [round(v * 1000) for v in box] + [round(W / H * 1000)]


def add_crops(products, previous):
    """Reuse last week's box when the photo URL is unchanged; measure the rest."""
    old = {}
    for p in previous:
        for c in p.get("colors") or []:
            for side, key in (("f", "front_flat"), ("b", "back_flat")):
                u = (c.get("images") or {}).get(key)
                b = (c.get("crop") or {}).get(side)
                if u and b:
                    old[u] = b
    todo = []
    for p in products:
        for c in p["colors"]:
            for side, key in (("f", "front_flat"), ("b", "back_flat")):
                u = c["images"].get(key)
                if u and u not in old:
                    todo.append(u)
    measured = 0
    if todo:
        try:
            import numpy, PIL  # noqa: F401
            from concurrent.futures import ThreadPoolExecutor

            def one(u):
                try:
                    return u, measure_crop(u)
                except Exception:
                    return u, None
            with ThreadPoolExecutor(12) as ex:
                for u, box in ex.map(one, sorted(set(todo))):
                    if box:
                        old[u] = box
                        measured += 1
        except ImportError:
            log("crop boxes skipped: Pillow/numpy not installed (photos show whole)")
    applied = 0
    for p in products:
        for c in p["colors"]:
            crop = {}
            for side, key in (("f", "front_flat"), ("b", "back_flat")):
                u = c["images"].get(key)
                if u and u in old:
                    crop[side] = old[u]
            if crop:
                c["crop"] = crop
                applied += 1
    log(f"crop boxes: {applied} colours cropped ({measured} newly measured)")


# ---------------------------------------------------------------- build
def build(style, skus, site_keys, site_brand_style):
    brand, st = style["brandName"], str(style["styleName"]).strip()
    title = re.sub(r"\s+", " ", style.get("title") or st).strip()

    if norm(brand) + "|" + norm(st) in site_brand_style:
        return None, f"{brand} {st}: already on the site, skipped (existing product wins)"

    key = st
    if norm(st) in site_keys:
        key = f"{BRANDS.get(brand, norm(brand)[:3])}-{st}"
        log(f"{brand} {st}: style number already used by another brand on the site, added as {key}")

    # S&S prices each colour separately: most colours share one price, while
    # some (camo, tie-dye, heathers...) cost more. The site has one blank price
    # per style, so the style is priced at its USUAL colour price - the price
    # most colours have (anything within 10% counts, priced at the dearest of
    # them) - and size upcharges come from those colours.
    # Colours that cost more than that are "specialty" (camo, tie-dye, pigment
    # dyed ...) and follow PREMIUM:
    #   price - (default, Austin 2026-11-20) kept in the same product with
    #           colors[].upcharge = their extra blank cost; the product page and
    #           the checkout Worker add it to case_price when that colour is picked
    #   hide  - not shown
    #   max   - every colour priced at the dearest colour (overcharges most)
    grid, colours = collections.defaultdict(dict), collections.OrderedDict()
    for k in sorted(skus, key=lambda k: (str(k.get("colorName")), str(k.get("sizeOrder") or ""))):
        pr = price_of(k)
        if pr <= 0:
            continue
        cname = k.get("colorName") or "Standard"
        sz = size_name(k.get("sizeName"))
        grid[cname][sz] = max(grid[cname].get(sz, 0), pr)
        colours.setdefault(cname, k)
    if not grid:
        return None, f"{brand} {st}: no price, skipped"

    def base_of(g):
        # the regular size: OSFA for a cap that also comes in an XL fit
        # (Imperial X210P), XS-XL for apparel, otherwise the cheapest size
        if "OSFA" in g:
            return g["OSFA"]
        return min([v for s, v in g.items() if s in ("XS", "S", "M", "L", "XL")] or list(g.values()))

    cbase = {c: round(base_of(g), 2) for c, g in grid.items()}
    counts = collections.Counter(cbase.values())
    usual = min(counts, key=lambda v: (-counts[v], v))
    # within 10% of the usual price counts as the same tier, priced at the
    # dearest colour in it so nothing is undercharged
    premium = {c for c, b in cbase.items() if b > usual * 1.10 + 0.005}
    if PREMIUM == "max":
        regular = set(grid)
    else:
        regular = set(grid) - premium
    shown = set(grid) - premium if PREMIUM == "hide" else set(grid)
    base = max(cbase[c] for c in regular)
    if premium:
        pct = round(100 * (max(cbase[c] for c in premium) / usual - 1))
        PREMIUMS.append((brand, st, len(premium), len(grid), pct))
        log(f"{brand} {st}: {len(premium)} of {len(grid)} colours cost more than the usual colour "
            f"(up to +{pct}%), {'hidden' if PREMIUM == 'hide' else 'priced separately' if PREMIUM == 'price' else 'style priced at the dearest'}: "
            f"{', '.join(sorted(premium))}")
    by_size = {}
    for c in regular:
        for sz, v in grid[c].items():
            by_size[sz] = max(by_size.get(sz, 0), v)
    upcharges = {s: round(v - base, 2) for s, v in by_size.items() if v - base > 0.004}
    sizes = sorted(by_size, key=size_key)
    colours = collections.OrderedDict((c, k) for c, k in colours.items() if c in shown)

    out_colours, no_back = [], 0
    for name, k in colours.items():
        front = img(k.get("colorFrontImage"))
        if not front:
            log(f"{brand} {st} {name}: no flat front photo, colour hidden")
            continue
        back = img(k.get("colorBackImage"))
        if not back:
            no_back += 1
        hx = str(k.get("color1") or "").lstrip("#")
        gallery = [u for u in (img(k.get("colorOnModelBackImage")), img(k.get("colorOnModelSideImage")),
                               img(k.get("colorDirectSideImage"))) if u]
        extra = round(cbase[name] - base, 2) if (PREMIUM == "price" and name in premium) else 0
        out_colours.append({
            "name": re.sub(r"\s+", " ", name).strip(),
            "code": k.get("colorCode") or name,
            "hex": ("#" + hx.upper()) if re.fullmatch(r"[0-9A-Fa-f]{6}", hx) else "#CCCCCC",
            "pms": None,
            "images": {"front_flat": front, "back_flat": back,
                       "front_model": img(k.get("colorOnModelFrontImage")),
                       "back_model": None, "side_model": None, "gallery": gallery},
        })
        if extra > 0.004:
            out_colours[-1]["upcharge"] = extra
    if not out_colours:
        return None, f"{brand} {st}: no colour has a flat front photo, skipped"
    if no_back:
        log(f"{brand} {st}: {no_back} colour(s) without a flat back photo (Back button hidden)")

    try:
        weight = round(float(next(k["unitWeight"] for k in skus if k.get("unitWeight"))), 2)
    except (StopIteration, TypeError, ValueError):
        weight = None
    return {
        "style": key,
        "name": f"{brand} {title}. {key}",
        "brand": brand,
        "category": category_for(style.get("baseCategory"), title),
        "subcategory": style.get("baseCategory") or "",
        "description": clean_desc(style.get("description")) or title,
        "case_price": round(base, 2),
        "case_sale_price": None, "sale_start_date": None, "sale_end_date": None,
        "msrp": None,
        "piece_weight_lbs": weight,
        "product_status": "Regular",
        "discontinued": False,
        "available_sizes": sizes,
        "size_upcharges": upcharges,
        "colors": out_colours,
        "source": "ss",
        "vendor_style": st,
        "spec_sheet": None,
        "decoration_spec_sheet": None,
    }, None


def main():
    if not (ACCT and KEY):
        print("::error::SS_ACCOUNT / SS_API_KEY missing")
        return 1

    # What the site already sells (SanMar, Lane Seven, PCNA ...), never S&S itself.
    site_keys, site_brand_style = set(), set()
    try:
        for p in json.load(open(CATALOG, encoding="utf-8")).get("products", []):
            if p.get("source") == "ss":
                continue
            site_keys.add(norm(p.get("style")))
            site_brand_style.add(norm(p.get("brand")) + "|" + norm(p.get("style")))
            if p.get("vendor_style"):
                site_brand_style.add(norm(p.get("brand")) + "|" + norm(p.get("vendor_style")))
    except Exception as e:
        print(f"::error::{CATALOG} unreadable ({e}) - cannot check for duplicates, not overwriting {OUT}")
        return 1

    styles = get("/styles/")
    mine = [s for s in styles if s.get("brandName") in BRANDS]
    if not mine:
        print(f"::error::S&S returned no styles for {', '.join(BRANDS)} - not overwriting {OUT}")
        return 1

    skus = collections.defaultdict(list)
    ids = [str(s["styleID"]) for s in mine]
    for i in range(0, len(ids), 20):
        for k in get("/products/", {"styleid": ",".join(ids[i:i + 20])}):
            skus[k.get("styleID")].append(k)

    # Which S&S price is lowest? Counts only, no values (public summary).
    cmp = collections.Counter()
    for ks in skus.values():
        for k in ks:
            cu, ca = float(k.get("customerPrice") or 0), float(k.get("casePrice") or 0)
            if cu and ca:
                cmp["account price below case price" if cu < ca - 0.004 else
                    "account price above case price" if cu > ca + 0.004 else "account price = case price"] += 1
    log("price check: " + ", ".join(f"{k} {v}" for k, v in sorted(cmp.items())))

    products, skipped = [], []
    for s in sorted(mine, key=lambda s: (s["brandName"], str(s["styleName"]))):
        res, why = build(s, skus.get(s["styleID"], []), site_keys, site_brand_style)
        if res:
            products.append(res)
        else:
            skipped.append(why)

    if len(products) < 0.7 * len(mine):
        print(f"::error::Only {len(products)}/{len(mine)} styles built - not overwriting {OUT}")
        print("\n".join(skipped + LOG))
        return 1

    previous = []
    if os.path.exists(OUT):
        try:
            previous = json.load(open(OUT, encoding="utf-8")).get("products", [])
        except Exception:
            pass
    add_crops(products, previous)

    doc = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "source": "S&S Activewear API v2", "brands": sorted(BRANDS),
           "product_count": len(products), "products": products}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)

    # Public summary: counts and names only, never prices.
    per_brand = collections.Counter(p["brand"] for p in products)
    cats = collections.Counter(p["category"] for p in products)
    lines = ["# S&S Activewear sync", "",
             f"- Styles from S&S: {len(mine)} | on the site: {len(products)} | skipped: {len(skipped)}",
             "- Brands: " + ", ".join(f"{b} {n}" for b, n in sorted(per_brand.items())),
             "- Colours: " + str(sum(len(p['colors']) for p in products)),
             "- Categories: " + ", ".join(f"{k} {v}" for k, v in cats.most_common()), ""]
    if PREMIUMS:
        lines += [f"## Colours that cost more than the style's usual colour ({PREMIUM})", "",
                  f"- {len(PREMIUMS)} styles, {sum(x[2] for x in PREMIUMS)} colours", ""]
        lines += [f"- {b} {s}: {n} of {t} colours, up to +{p}%" for b, s, n, t, p in PREMIUMS] + [""]
    if skipped:
        lines += ["## Skipped", ""] + [f"- {s}" for s in skipped] + [""]
    if LOG:
        lines += ["## Notes", ""] + [f"- {l}" for l in LOG] + [""]
    lines += ["## Styles", "", "| Key | Brand | Name | Category | Colours | Sizes |", "|---|---|---|---|---|---|"]
    for p in products:
        lines.append(f"| {p['style']} | {p['brand']} | {p['name'][len(p['brand']) + 1:70]} | {p['category']} | "
                     f"{len(p['colors'])} | {p['available_sizes'][0]}-{p['available_sizes'][-1]} |")
    text = "\n".join(lines) + "\n"
    print(text)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        open(sp, "a", encoding="utf-8").write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
