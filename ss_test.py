"""S&S Activewear connection test (manual GitHub Action: "S&S connection test").

Checks the S&S REST API login and reports what the three starting brands
(Imperial, Independent Trading Co., Valucap) look like, so the real sync can
be built from facts rather than guesses.

  - Secrets: SS_ACCOUNT (account number) and SS_API_KEY. Basic auth.
  - Public output (the run summary and the log) shows COUNTS ONLY. No price
    ever appears in it: this repo is public, and so are its Action logs.
  - The artifact `ss-test` (3 days) holds styles.json: the style list, colors,
    sizes, photo coverage and which price fields S&S fills in. No price
    values and no ratios between them (a ratio to the public list price
    would reveal our cost).
  - Duplicate check: every S&S style number is compared with the styles
    already on the site (products.json). Anything that matches is listed;
    the real sync will skip it, because the existing product always wins.

Standard library only. Docs: https://api.ssactivewear.com/V2/Default.aspx
"""
import base64, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

BASE = "https://api.ssactivewear.com/v2"
WANT = ["Imperial", "Independent Trading Co.", "Valucap"]
OUT = os.environ.get("SS_OUT", "ss-out")
PRICE_FIELDS = ["piecePrice", "dozenPrice", "casePrice", "customerPrice", "salePrice", "mapPrice"]
IMG_FIELDS = ["colorFrontImage", "colorBackImage", "colorSideImage", "colorDirectSideImage",
              "colorOnModelFrontImage", "colorOnModelBackImage", "colorOnModelSideImage", "colorSwatchImage"]

acct, key = os.environ.get("SS_ACCOUNT", "").strip(), os.environ.get("SS_API_KEY", "").strip()
lines = []


def say(s=""):
    print(s)
    lines.append(s)


def finish(code=0):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    sys.exit(code)


if not acct or not key:
    say("## S&S connection test\n\n**Missing secrets.** Add `SS_ACCOUNT` and `SS_API_KEY` under "
        "Settings → Secrets and variables → Actions, then run again.")
    finish(1)

AUTH = "Basic " + base64.b64encode(f"{acct}:{key}".encode()).decode()


def get(path, params=None, tries=3):
    url = BASE + path + ("?" + urllib.parse.urlencode(params, safe=",") if params else "")
    for i in range(tries):
        req = urllib.request.Request(url, headers={"Authorization": AUTH, "Accept": "application/json",
                                                   "User-Agent": "AlivePrintShop-catalog-test"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                remaining = r.headers.get("X-Rate-Limit-Remaining")
                return json.loads(r.read().decode("utf-8") or "[]"), remaining
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(5 * (i + 1))
                continue
            if e.code == 404:          # S&S answers 404 for "nothing matched"
                return [], None
            raise RuntimeError(f"HTTP {e.code} on {path}: {body}")


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


say("## S&S Activewear connection test\n")

# 1. Login + brand names
try:
    brands, rl = get("/brands/")
except RuntimeError as e:
    msg = str(e)
    say("**Login failed.** " + ("Check the account number and API key." if " 401 " in msg or "HTTP 401" in msg else msg))
    finish(1)
say(f"- Login: **OK**. {len(brands)} brands on the account. Rate limit remaining: {rl or 'not reported'}.")
names = {b.get("name", ""): b for b in brands}
found = {}
for w in WANT:
    hit = [n for n in names if norm(n) == norm(w)] or [n for n in names if norm(w)[:8] in norm(n)]
    found[w] = hit
    say(f"- Brand **{w}**: " + (", ".join(f"`{h}`" for h in hit) if hit else "NOT FOUND"))
brand_names = sorted({h for v in found.values() for h in v})
if not brand_names:
    finish(1)

# 2. Styles for those brands
styles, _ = get("/styles/", {"fields": "styleID,partNumber,brandName,styleName,title,baseCategory,categories,newStyle,styleImage,companionGroup"})
mine = [s for s in styles if s.get("brandName") in brand_names]
say(f"\n### Styles\n- All S&S styles: {len(styles)}. For these brands: **{len(mine)}**.")

# 3. Duplicate check against the site
site = set()
try:
    with open("products.json", encoding="utf-8") as f:
        for p in json.load(f).get("products", []):
            site.add(norm(p.get("style")))
except Exception as e:
    say(f"- (products.json not read: {e})")
dups = [s for s in mine if norm(s.get("styleName")) in site]
say(f"- Already on the site (same style number): **{len(dups)}**" +
    (": " + ", ".join(f"{s['brandName']} {s['styleName']}" for s in dups) if dups else ""))

# 4. SKUs per style
by_style = {}
ids = [str(s["styleID"]) for s in mine]
fields_seen, price_filled = set(), {f: 0 for f in PRICE_FIELDS}
for i in range(0, len(ids), 20):
    chunk = ids[i:i + 20]
    skus, rl = get("/products/", {"styleid": ",".join(chunk)})
    for k in skus:
        fields_seen.update(k.keys())
        by_style.setdefault(k.get("styleID"), []).append(k)
        for f in PRICE_FIELDS:
            if k.get(f):
                price_filled[f] += 1
    time.sleep(0.5)
total_skus = sum(len(v) for v in by_style.values())
say(f"- SKUs (color × size) for these styles: **{total_skus}**. Rate limit remaining: {rl or 'not reported'}.")

say("\n### Price fields (how many SKUs have each one filled in; no values shown)")
for f in PRICE_FIELDS:
    say(f"- `{f}`: {price_filled[f]}/{total_skus}")

# 5. Per style summary (no prices)
report, cats = [], {}
for s in mine:
    ks = by_style.get(s["styleID"], [])
    colors = {}
    for k in ks:
        c = colors.setdefault(k.get("colorName"), {"hex": k.get("color1"), "sizes": [], "images": {f: bool(k.get(f)) for f in IMG_FIELDS}})
        c["sizes"].append(k.get("sizeName"))
    base = None
    up = 0
    pps = [(k.get("sizeOrder") or "", k.get("piecePrice") or 0) for k in ks]
    if pps:
        base = min(p for _, p in pps if p) if any(p for _, p in pps) else None
        up = len({k.get("sizeName") for k in ks if base and (k.get("piecePrice") or 0) > base + 0.005})
    sizes = []
    for k in sorted(ks, key=lambda k: str(k.get("sizeOrder") or "")):
        if k.get("sizeName") not in sizes:
            sizes.append(k.get("sizeName"))
    front = sum(1 for c in colors.values() if c["images"]["colorFrontImage"])
    back = sum(1 for c in colors.values() if c["images"]["colorBackImage"])
    cats[s.get("baseCategory")] = cats.get(s.get("baseCategory"), 0) + 1
    report.append({
        "brand": s.get("brandName"), "style": s.get("styleName"), "styleID": s.get("styleID"),
        "partNumber": s.get("partNumber"), "title": s.get("title"), "baseCategory": s.get("baseCategory"),
        "categories": s.get("categories"), "newStyle": s.get("newStyle"),
        "on_site_already": norm(s.get("styleName")) in site,
        "colors": len(colors), "colors_with_front_photo": front, "colors_with_back_photo": back,
        "sizes": sizes, "sizes_with_upcharge": up, "has_price": bool(base), "skus": len(ks),
        "sample_images": {f: next((k.get(f) for k in ks if k.get(f)), None) for f in IMG_FIELDS},
        "color_list": [{"name": n, "hex": c["hex"], **{"photo_" + f: v for f, v in c["images"].items()}} for n, c in colors.items()],
    })

say("\n### By brand")
for b in brand_names:
    rs = [r for r in report if r["brand"] == b]
    say(f"- **{b}**: {len(rs)} styles, {sum(r['colors'] for r in rs)} colors, "
        f"{sum(1 for r in rs if not r['has_price'])} with no price, "
        f"{sum(1 for r in rs if r['colors_with_front_photo'] == 0)} with no front photo")
say("\n### Categories (S&S baseCategory)")
for c, n in sorted(cats.items(), key=lambda x: -x[1]):
    say(f"- {c or '(none)'}: {n}")
say("\n### Styles")
say("| Brand | Style | Title | Category | Colors | Front photos | Back photos | Sizes | Upcharge sizes | On site |")
say("|---|---|---|---|---|---|---|---|---|---|")
for r in sorted(report, key=lambda r: (r["brand"], r["style"] or "")):
    say(f"| {r['brand']} | {r['style']} | {(r['title'] or '')[:50]} | {r['baseCategory']} | {r['colors']} | "
        f"{r['colors_with_front_photo']} | {r['colors_with_back_photo']} | {' '.join(map(str, r['sizes']))[:40]} | "
        f"{r['sizes_with_upcharge']} | {'YES' if r['on_site_already'] else ''} |")
say("\n### SKU fields S&S returns\n" + ", ".join(f"`{f}`" for f in sorted(fields_seen)))

os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "styles.json"), "w", encoding="utf-8") as f:
    json.dump({"brands": brand_names, "styles": report, "sku_fields": sorted(fields_seen),
               "price_fields_filled": price_filled}, f, indent=1)
say(f"\nSaved `{OUT}/styles.json` (no prices) to the `ss-test` artifact.")
finish(0)
