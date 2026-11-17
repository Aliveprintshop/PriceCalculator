#!/usr/bin/env python3
"""
PCNA weekly sync -> pcna-products.json (customer prices only).

Runs in GitHub Actions with the PCNA_ID / PCNA_PASSWORD secrets.

For every product ID in pcna-picks.json it pulls, from PCNA's PromoStandards
services:
  GetProduct (v2)            name, brand, description, colors/parts, image
  GetMediaContent            one photo per color
  GetFobPoints               ship-from point
  GetConfigurationAndPricing List (= PCNA "coded") and Net, Decorated

and writes ONE all-inclusive price per piece for each quantity break, per
decoration method (Laser / Print), using APS's pricing rule (Nov 2026):

  price/pc = coded product + coded run charge
           + coded setup / qty
           + freight / qty
  freight  = tier% x (Net product cost x qty)   <- tiers below

Net is used ONLY inside this script to size freight. It is never written to
the output: pcna-products.json is published on the public site.

The output uses the site's existing "all-inclusive" product shape (the same
one drinkware uses): _drinkware:true + _dwMatrix[qtyBreak][1] = price/pc.
A product that offers both Laser and Print becomes two entries: the Print
one is listed, and a hidden "<id>-L" sibling holds the Laser prices. The
product page switches between them with a Decoration dropdown.
"""
import os, re, sys, json, time, html
import urllib.request, urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

PCNA_ID = os.environ.get("PCNA_ID", "").strip()
PCNA_PW = os.environ.get("PCNA_PASSWORD", "").strip()
PICKS = os.environ.get("PCNA_PICKS", "pcna-picks.json")
OUT = os.environ.get("PCNA_OUT_FILE", "pcna-products.json")
WORKERS = int(os.environ.get("PCNA_WORKERS", "4"))

PD = "https://psproductdata200.pcna.online"
PPC = "https://pspriceconfig100.pcna.online"
MED = "https://psmediacontent110.pcna.online"

# Freight as a % of APS product cost (Net x qty), scaled down on bigger orders.
# Calibrated on 3 real quotes to Las Vegas (Nov 2026); Austin sends actual
# freight from new orders so these can be tuned.
FREIGHT_TIERS = [(300, 0.65), (750, 0.30), (1500, 0.20), (3000, 0.15), (None, 0.10)]

# Pick-list group -> site category (must match CATEGORY_BUCKETS in index.html)
CATEGORY = {
    "Drinkware": "Drinkware",
    "Journals & Notebooks": "Journals & Notebooks",
    "Pens": "Pens",
    "Technology": "Technology",
    "Keychains": "Keychains",
}


def freight_pct(net_subtotal):
    for lim, pct in FREIGHT_TIERS:
        if lim is None or net_subtotal < lim:
            return pct
    return FREIGHT_TIERS[-1][1]


# ------------------------------------------------------------------ SOAP
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def env(svc, ver, op, body):
    ns = (f'xmlns:ns="http://www.promostandards.org/WSDL/{svc}/{ver}/" '
          f'xmlns:shar="http://www.promostandards.org/WSDL/{svc}/{ver}/SharedObjects/"')
    return ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'{ns}><soapenv:Header/><soapenv:Body><ns:{op}>{body}</ns:{op}>'
            '</soapenv:Body></soapenv:Envelope>')


CREDS = lambda: f"<shar:id>{esc(PCNA_ID)}</shar:id><shar:password>{esc(PCNA_PW)}</shar:password>"
LOC = ("<shar:localizationCountry>US</shar:localizationCountry>"
       "<shar:localizationLanguage>en</shar:localizationLanguage>")


def post(url, action, xml, tries=3):
    last = ""
    for i in range(tries):
        req = urllib.request.Request(url, data=xml.encode(), method="POST", headers={
            "Content-Type": "text/xml; charset=utf-8", "SOAPAction": action})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e.read().decode("utf-8", "replace")
            if e.code < 500:
                return last
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(3 * (i + 1))
    return last


L = lambda t: t.rsplit("}", 1)[-1]


def parse(x):
    try:
        return ET.fromstring(x)
    except ET.ParseError:
        return None


def kids(e, name):
    return [c for c in e.iter() if L(c.tag) == name] if e is not None else []


def first(e, name):
    for c in kids(e, name):
        if c.text and c.text.strip():
            return c.text.strip()
    return ""


def direct(e, name):
    """Text of a DIRECT child (not a descendant)."""
    for c in list(e):
        if L(c.tag) == name and c.text:
            return c.text.strip()
    return ""


def err(root, raw):
    d = first(root, "description")
    return d or raw[:200]


def get_product(pid):
    b = "<shar:wsVersion>2.0.0</shar:wsVersion>" + CREDS() + LOC + f"<shar:productId>{esc(pid)}</shar:productId>"
    return post(PD, "getProduct", env("ProductDataService", "2.0.0", "GetProductRequest", b))


def get_media(pid):
    b = ("<shar:wsVersion>1.1.0</shar:wsVersion>" + CREDS() + "<shar:cultureName>en-US</shar:cultureName>"
         f"<shar:mediaType>Image</shar:mediaType><shar:productId>{esc(pid)}</shar:productId>")
    return post(MED, "getMediaContent", env("MediaService", "1.0.0", "GetMediaContentRequest", b))


def get_fob(pid):
    b = "<shar:wsVersion>1.0.0</shar:wsVersion>" + CREDS() + f"<shar:productId>{esc(pid)}</shar:productId>" + LOC
    return post(PPC, "getFobPoints", env("PricingAndConfiguration", "1.0.0", "GetFobPointsRequest", b))


def get_price(pid, fob, ptype):
    b = ("<shar:wsVersion>1.0.0</shar:wsVersion>" + CREDS() + f"<shar:productId>{esc(pid)}</shar:productId>"
         f"<shar:currency>USD</shar:currency><shar:fobId>{esc(fob)}</shar:fobId>"
         f"<shar:priceType>{ptype}</shar:priceType>" + LOC +
         "<shar:configurationType>Decorated</shar:configurationType>")
    return post(PPC, "getConfigurationAndPricing",
                env("PricingAndConfiguration", "1.0.0", "GetConfigurationAndPricingRequest", b))


# ------------------------------------------------------------------ parsing
def clean(s):
    s = html.unescape(s or "")
    s = re.sub(r"[™®]", "", s)          # TM / (R)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def part_breaks(root):
    """{partId: [(minQty, price), ...]} from a pricing response."""
    out = {}
    for part in kids(root, "Part"):
        pid = direct(part, "partId")
        rows = []
        for pp in kids(part, "PartPrice"):
            try:
                rows.append((int(float(first(pp, "minQuantity"))), float(first(pp, "price"))))
            except ValueError:
                pass
        if pid and rows:
            out[pid] = sorted(rows)
    return out


def at(rows, q):
    """Price at qty q from sorted [(minQty, price)] (largest minQty <= q)."""
    v = None
    for mq, p in rows:
        if q >= mq:
            v = p
    return v if v is not None else (rows[0][1] if rows else None)


def charge_rows(ch, colors=1):
    rows = []
    for cp in kids(ch, "ChargePrice"):
        try:
            y = int(float(first(cp, "yMinQty") or 1))
            if y != colors:
                continue
            rows.append((int(float(first(cp, "xMinQty") or 1)), float(first(cp, "price") or 0)))
        except ValueError:
            pass
    return sorted(rows)


def decorations(root):
    """[{name, location, size, charges:[Charge elements]}] in location order."""
    out = []
    locs = kids(root, "Location")
    # defaultLocation / locationRank, when present, decide the order
    def rank(loc):
        r = first(loc, "locationRank")
        d = first(loc, "defaultLocation").lower() == "true"
        try:
            r = int(r)
        except ValueError:
            r = 999
        return (0 if d else 1, r)
    for loc in sorted(locs, key=rank):
        lname = direct(loc, "locationName")
        for d in kids(loc, "Decoration"):
            h, w = first(d, "decorationHeight"), first(d, "decorationWidth")
            dia = first(d, "decorationDiameter")
            size = ""
            try:
                if float(h or 0) and float(w or 0):
                    size = f'{float(w):g}" x {float(h):g}"'
                elif float(dia or 0):
                    size = f'{float(dia):g}" diameter'
            except ValueError:
                pass
            out.append({"name": direct(d, "decorationName"), "location": clean(lname),
                        "size": size, "el": d})
    return out


def pick(decos, kind):
    names = [d for d in decos if d["name"]]
    if kind == "laser":
        order = [lambda n: n == "laser",
                 lambda n: "laser" in n and "plus" not in n,
                 lambda n: "laser" in n]
    else:
        order = [lambda n: "silkscreen" in n or "silk screen" in n,
                 lambda n: "pad" in n,
                 lambda n: "screen" in n,
                 lambda n: "color print" in n and "digital" not in n,
                 lambda n: "digital" in n or "full color" in n,
                 lambda n: "print" in n or "transfer" in n]
    for test in order:
        for d in names:
            if test(d["name"].lower()):
                return d
    return None


def deco_costs(d):
    """(setup, run_rows) for a 1-color, first-location imprint of this decoration."""
    setup, run, run_loc1 = None, None, None
    for ch in kids(d["el"], "Charge"):
        typ = first(ch, "chargeType").lower()
        nm = first(ch, "chargeName").upper()
        rows = charge_rows(ch, 1)
        if not rows:
            continue
        if typ == "setup" and "MULTI" not in nm and setup is None:
            setup = rows[0][1]
        elif typ == "run":
            if "LOC 1" in nm or "LOCATION1" in nm or "LOC1" in nm:
                run_loc1 = rows
            elif run is None:
                run = rows
    return (setup or 0.0), (run_loc1 if run_loc1 is not None else (run or []))


HEX_GUESS = [
    ("black", "#1c1c1e"), ("white", "#ffffff"), ("navy", "#1b2a4a"), ("royal", "#2251b5"),
    ("blue", "#2f6fb5"), ("red", "#c8102e"), ("green", "#2e8b57"), ("orange", "#ff6a13"),
    ("yellow", "#ffd200"), ("purple", "#6a3d9a"), ("pink", "#f4a6c0"), ("gray", "#8a8d91"),
    ("grey", "#8a8d91"), ("silver", "#c0c0c0"), ("gold", "#c9a227"), ("brown", "#7b5a3c"),
    ("tan", "#d2b48c"), ("teal", "#2bb3a3"), ("clear", "#e8eef2"), ("wood", "#a0754b"),
    ("bamboo", "#c8a96b"), ("copper", "#b87333"), ("stainless", "#b8bcc0"), ("charcoal", "#36454f"),
    ("cream", "#f3ead7"), ("ivory", "#f3ead7"), ("mint", "#a8e6cf"), ("lime", "#9acd32"),
    ("aqua", "#4fd1c5"), ("maroon", "#7a1f2b"), ("burgundy", "#7a1f2b"),
]


def guess_hex(name):
    n = (name or "").lower()
    for k, v in HEX_GUESS:
        if k in n:
            return v
    return "#cccccc"


def big(url):
    return re.sub(r"/t_PS_[A-Z0-9]+/", "/t_PS_EXTRALARGE2/", url or "")


def parse_media(root):
    """{partId: best photo url}. The customer places their own logo on the
    photo, so a clean BLANK front shot of that color wins; PCNA's decorated
    sample, group shots and accessory/alternate shots are fallbacks only."""
    best = {}
    for m in kids(root, "MediaContent"):
        part = direct(m, "partId")
        url = direct(m, "url")
        if not part or not url:
            continue
        cls = {(t.text or "").strip().lower() for t in kids(m, "classTypeName")}
        name = url.rsplit("/", 1)[-1].upper()
        front = "front" in cls
        if front and "blank" in cls and "internal use" not in cls and "_GRP" not in name:
            score = 0
        elif front and "blank" in cls and "_GRP" not in name:
            score = 1
        elif front and "decorated" in cls and "_GRP" not in name:
            score = 2
        elif "part default image" in cls and "_GRP" not in name:
            score = 3
        elif front and "alternate" not in cls:
            score = 4
        elif "alternate" not in cls:
            score = 5
        else:
            score = 6
        if "-" in name.rsplit(".", 1)[0][-3:]:   # prefer the un-numbered original
            score += 0.1
        if part not in best or score < best[part][0]:
            best[part] = (score, big(url))
    return {k: v[1] for k, v in best.items()}


def parse_product(root):
    prod = next(iter(kids(root, "Product")), root)
    name = clean(first(prod, "productName"))
    brand = clean(first(prod, "productBrand"))
    line = clean(first(prod, "lineName"))
    descs = [clean(e.text) for e in kids(prod, "description") if e.text and e.text.strip()]
    # PCNA puts price codes in some descriptions; drop those tokens
    desc = " ".join(d for d in descs if not re.search(r"(USD|CAD)-(List|Net)-", d))
    feats = [clean(e.text) for e in kids(prod, "productMarketingPoint") if e.text]
    feats += [clean(first(mp, "pointCopy")) for mp in kids(prod, "ProductMarketingPoint")]
    feats = [f for f in dict.fromkeys(feats)
             if f and len(f) > 3 and f.lower() != 'none' and '/' not in f and not f.isdigit()][:8]
    parts = []
    for pp in kids(prod, "ProductPart"):
        pid = direct(pp, "partId")
        cname = clean(first(pp, "colorName")) or clean(first(pp, "standardColorName"))
        cname = re.sub(r"\s*\([A-Z0-9]{1,6}\)\s*$", "", cname)   # 'Black (BK)' -> 'Black'
        hx = first(pp, "hex")
        if hx and not hx.startswith("#"):
            hx = "#" + hx
        if pid:
            parts.append({"partId": pid, "color": cname, "hex": hx})
    image = big(first(prod, "primaryImageUrl"))
    return {"name": name, "brand": brand or line, "line": line, "desc": desc[:900],
            "features": feats, "parts": parts, "image": image,
            "closeout": first(prod, "isCloseout").lower() == "true"}


# ------------------------------------------------------------------ build
def build(pid, group):
    log = []
    raw = get_product(pid)
    r = parse(raw)
    info = parse_product(r)
    if not info["name"]:
        return None, [f"{pid}: GetProduct failed: {err(r, raw)}"]
    media = parse_media(parse(get_media(pid)))

    fr = parse(get_fob(pid))
    fobs = [first(f, "fobId") for f in kids(fr, "FobPoint")]
    if not fobs:
        return None, [f"{pid}: no FOB point"]
    fob = fobs[0]

    lr = parse(get_price(pid, fob, "List"))
    nr = parse(get_price(pid, fob, "Net"))
    lb, nb = part_breaks(lr), part_breaks(nr)
    if not lb or not nb:
        return None, [f"{pid}: pricing missing (List {bool(lb)}, Net {bool(nb)})"]
    # Every part of a PCNA style is priced the same; use the first one, but
    # warn if the colors differ.
    # Colors are usually priced alike. When they aren't, price every color at
    # the dearest one, so no color is ever under-quoted.
    p0 = max(lb, key=lambda k: lb[k][0][1])
    list_rows, net_rows = lb[p0], nb.get(p0) or next(iter(nb.values()))
    if any(v != list_rows for v in lb.values()):
        cheap = min(v[0][1] for v in lb.values())
        log.append(f"{pid}: colors priced differently (${cheap:.2f}-${list_rows[0][1]:.2f} list); priced at {p0}")
    breaks = [q for q, _ in list_rows]

    decos = decorations(lr)
    methods = []
    for kind in ("print", "laser"):
        d = pick(decos, kind)
        if d:
            methods.append((kind, d))
    if not methods:
        return None, [f"{pid}: no Laser or Print decoration ({[d['name'] for d in decos]})"]

    # colors
    colors, seen = [], set()
    for part in info["parts"]:
        cname = part["color"] or part["partId"]
        if cname in seen:
            continue
        seen.add(cname)
        img = media.get(part["partId"]) or info["image"]
        colors.append({"name": cname, "hex": part["hex"] or guess_hex(cname), "sku": part["partId"],
                       "images": {"front_flat": img}})
    if not colors:
        colors = [{"name": "Standard", "hex": "#cccccc", "sku": pid, "images": {"front_flat": info["image"]}}]

    entries = []
    for kind, d in methods:
        setup, run_rows = deco_costs(d)
        matrix = {}
        for q in breaks:
            lp, np_ = at(list_rows, q), at(net_rows, q)
            run = at(run_rows, q) if run_rows else 0.0
            net_sub = np_ * q
            freight = freight_pct(net_sub) * net_sub
            unit = lp + (run or 0.0) + setup / q + freight / q
            matrix[str(q)] = {"1": round(unit, 2)}
        label = ("Laser engraved" if kind == "laser"
                 else "Full-color print" if re.search("digital|full color", d["name"], re.I)
                 else "1-color print")
        entries.append({"kind": kind, "matrix": matrix, "label": label, "deco": d})

    base = {
        "name": info["name"],
        "brand": info["brand"] or "PCNA",
        "category": CATEGORY.get(group, group),
        "subcategory": "",
        "description": info["desc"],
        "desc": info["desc"],
        "features": info["features"],
        "available_sizes": ["Qty"],
        "size_upcharges": {},
        "discontinued": False,
        "source": "pcna",
        "_pcna": True,
        "_pcnaId": pid,
        "_drinkware": True,
        "_maxInk": 1,
        "colors": colors,
    }
    out = []
    print_e = next((e for e in entries if e["kind"] == "print"), None)
    laser_e = next((e for e in entries if e["kind"] == "laser"), None)
    primary = print_e or laser_e
    for e in entries:
        is_primary = e is primary
        style = pid if is_primary else f"{pid}-L"
        p = dict(base)
        p.update({
            "style": style,
            "_dwMatrix": e["matrix"],
            "_decoLabel": e["label"],
            "_decoMethod": e["kind"],
            "_imprint": ", ".join(x for x in (e["deco"]["size"], e["deco"]["location"]) if x),
        })
        if not is_primary:
            p["_hidden"] = True
            p["name"] = info["name"]
        if print_e and laser_e:
            p["_decoOptions"] = [
                {"style": pid, "label": print_e["label"], "method": "print"},
                {"style": f"{pid}-L", "label": "Laser engraved", "method": "laser"},
            ]
        out.append(p)
    return out, log


def main():
    if not (PCNA_ID and PCNA_PW):
        print("PCNA_ID / PCNA_PASSWORD missing")
        return 1
    picks = json.load(open(PICKS, encoding="utf-8"))
    jobs = [(pid, grp) for grp, ids in picks.items() for pid in ids]
    products, logs, failed = [], [], []
    with ThreadPoolExecutor(WORKERS) as ex:
        for (pid, grp), fut in zip(jobs, [ex.submit(build, p, g) for p, g in jobs]):
            try:
                res, log = fut.result()
            except Exception as e:
                res, log = None, [f"{pid}: {type(e).__name__}: {e}"]
            logs += log
            if res:
                products += res
            else:
                failed.append(pid)

    listed = [p for p in products if not p.get("_hidden")]
    if len(listed) < 0.8 * len(jobs):
        print(f"::error::Only {len(listed)}/{len(jobs)} products built - not overwriting {OUT}")
        print("\n".join(logs))
        return 1

    doc = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "source": "PCNA PromoStandards", "pricing": "coded all-in incl. setup, run, freight",
           "product_count": len(listed), "products": products}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)

    lines = ["# PCNA sync", "",
             f"- Picks: {len(jobs)} | listed: {len(listed)} | laser siblings: {len(products) - len(listed)}",
             f"- Failed: {', '.join(failed) or 'none'}", ""]
    if logs:
        lines += ["## Notes", ""] + [f"- {l}" for l in logs]
    lines += ["", "## Sample prices (all-in per piece at the minimum)", "",
              "| ID | Product | Method | Min | $/pc at min |", "|---|---|---|---|---|"]
    for p in products[:12]:
        q = min(p["_dwMatrix"], key=int)
        lines.append(f"| {p['style']} | {p['name'][:40]} | {p['_decoLabel']} | {q} | {p['_dwMatrix'][q]['1']:.2f} |")
    text = "\n".join(lines) + "\n"
    print(text)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        open(sp, "a", encoding="utf-8").write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
