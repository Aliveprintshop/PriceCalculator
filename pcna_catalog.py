#!/usr/bin/env python3
"""
PCNA catalog pull (for product selection). Runs in GitHub Actions.

Credentials come from the PCNA_ID / PCNA_PASSWORD secrets.

Steps
  1. GetProductSellable -> all active product IDs.
  2. GetProduct for every ID -> name, brand, categories, description, colors,
     image, closeout flag.
  3. For products in the target categories (drinkware, journals/notebooks,
     pens, technology, keychains): GetFobPoints + Decorated List pricing ->
     minimum qty, List price breaks, decoration methods.
     List = PCNA's public MSRP, so it is safe in the artifact. No Net or
     Customer cost is pulled here.

Output (artifact "pcna-catalog"):
  pcna-catalog.json -- one record per product.
Run summary: counts by category only.

Standard library only.
"""
import os, re, sys, json, time, threading
import urllib.request, urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

PCNA_ID = os.environ.get("PCNA_ID", "").strip()
PCNA_PW = os.environ.get("PCNA_PASSWORD", "").strip()
OUT = os.environ.get("PCNA_OUT", "pcna-out")
WORKERS = int(os.environ.get("PCNA_WORKERS", "6"))

PD200 = "https://psproductdata200.pcna.online"
PD100 = "https://psproductdata100.pcna.online"   # ProductData v1.0.0
PPC = "https://pspriceconfig100.pcna.online"

TARGET = {
    "drinkware": r"drink|bottle|tumbler|mug|cup|flask|thermos|hydration|tea|coffee|growler|cooler",
    "journals": r"journal|notebook|notepad|planner|padfolio|portfolio|sticky|note ?book|moleskine",
    "pens": r"\bpens?\b|writing|stylus|pencil|marker|highlighter|rollerball|ballpoint",
    "technology": r"tech|power ?bank|charger|charging|speaker|audio|headphone|earbud|cable|usb|wireless|bluetooth|phone|tracker|electronic|mouse|webcam",
    "keychains": r"key ?chain|key ?ring|key ?fob|key ?tag|keyring|carabiner",
}
EXCLUDE = r"apparel|shirt|jacket|hoodie|sweat|polo|tee\b|headwear|cap\b|hat\b|vest|pullover|fleece|pant|sock|glove|beanie"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def env(ver_pd, op, body, svc="ProductDataService"):
    ns = (f'xmlns:ns="http://www.promostandards.org/WSDL/{svc}/{ver_pd}/" '
          f'xmlns:shar="http://www.promostandards.org/WSDL/{svc}/{ver_pd}/SharedObjects/"')
    return ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'{ns}><soapenv:Header/><soapenv:Body><ns:{op}>{body}</ns:{op}></soapenv:Body></soapenv:Envelope>')


def creds():
    return f"<shar:id>{esc(PCNA_ID)}</shar:id><shar:password>{esc(PCNA_PW)}</shar:password>"


LOC = ("<shar:localizationCountry>US</shar:localizationCountry>"
       "<shar:localizationLanguage>en</shar:localizationLanguage>")


def post(url, action, xml, timeout=120, tries=3):
    last = (0, "")
    for i in range(tries):
        req = urllib.request.Request(url, data=xml.encode(), method="POST", headers={
            "Content-Type": "text/xml; charset=utf-8", "SOAPAction": action})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = (e.code, e.read().decode("utf-8", "replace"))
            if e.code < 500:
                return last
        except Exception as e:
            last = (0, f"{type(e).__name__}: {e}")
        time.sleep(2 * (i + 1))
    return last


L = lambda t: t.rsplit("}", 1)[-1]


def parse(x):
    try:
        return ET.fromstring(x)
    except ET.ParseError:
        return None


def all_(root, name):
    return [e for e in root.iter() if L(e.tag) == name] if root is not None else []


def first(root, name):
    for e in all_(root, name):
        if e.text and e.text.strip():
            return e.text.strip()
    return ""


def err(root, raw):
    d = first(root, "description")
    c = first(root, "code")
    return f"[{c}] {d}" if d else raw[:160]


# ---------------------------------------------------------------- requests
def get_product_v2(pid):
    body = ("<shar:wsVersion>2.0.0</shar:wsVersion>" + creds() + LOC +
            f"<shar:productId>{esc(pid)}</shar:productId>")
    return post(PD200, "getProduct", env("2.0.0", "GetProductRequest", body))


def get_product_v1(pid):
    body = ("<shar:wsVersion>1.0.0</shar:wsVersion>" + creds() + LOC +
            f"<shar:productId>{esc(pid)}</shar:productId>")
    return post(PD100, "getProduct", env("1.0.0", "GetProductRequest", body))


PRODUCT_CALL = None   # chosen after probing


def fob_points(pid):
    body = ("<shar:wsVersion>1.0.0</shar:wsVersion>" + creds() +
            f"<shar:productId>{esc(pid)}</shar:productId>" + LOC)
    return post(PPC, "getFobPoints", env("1.0.0", "GetFobPointsRequest", body, "PricingAndConfiguration"))


def list_pricing(pid, fob):
    body = ("<shar:wsVersion>1.0.0</shar:wsVersion>" + creds() +
            f"<shar:productId>{esc(pid)}</shar:productId><shar:currency>USD</shar:currency>"
            f"<shar:fobId>{esc(fob)}</shar:fobId><shar:priceType>List</shar:priceType>" + LOC +
            "<shar:configurationType>Decorated</shar:configurationType>")
    return post(PPC, "getConfigurationAndPricing",
                env("1.0.0", "GetConfigurationAndPricingRequest", body, "PricingAndConfiguration"))


# ---------------------------------------------------------------- parsing
def parse_product(root):
    p = {}
    p["name"] = first(root, "productName")
    p["brand"] = first(root, "productBrand")
    descs = [e.text.strip() for e in all_(root, "description") if e.text and e.text.strip()]
    p["description"] = " ".join(descs)[:600]
    cats = []
    for c in all_(root, "ProductCategory"):
        cat, sub = first(c, "category"), first(c, "subCategory")
        s = " > ".join(x for x in (cat, sub) if x)
        if s and s not in cats:
            cats.append(s)
    p["categories"] = cats
    kws = [e.text.strip() for e in all_(root, "keyword") if e.text]
    p["keywords"] = kws[:15]
    colors = []
    for e in all_(root, "colorName"):
        if e.text and e.text.strip() and e.text.strip() not in colors:
            colors.append(e.text.strip())
    p["colors"] = colors
    p["parts"] = len(all_(root, "ProductPart")) or len({e.text for e in all_(root, "partId")})
    p["image"] = first(root, "primaryImageUrl") or first(root, "productImageUrl")
    p["closeout"] = any((e.text or "").strip().lower() == "true" for e in all_(root, "isCloseout"))
    p["line"] = first(root, "lineName")
    p["export"] = first(root, "export")
    return p


def parse_pricing(root):
    out = {"min_qty": None, "list_breaks": [], "methods": []}
    part = next(iter(all_(root, "Part")), None)
    if part is not None:
        rows = []
        for pp in all_(part, "PartPrice"):
            try:
                rows.append([int(float(first(pp, "minQuantity"))), round(float(first(pp, "price")), 2)])
            except ValueError:
                pass
        rows.sort()
        out["list_breaks"] = rows
        out["min_qty"] = rows[0][0] if rows else None
    for d in all_(root, "Decoration"):
        n = first(d, "decorationName")
        if n and n not in out["methods"]:
            out["methods"].append(n)
    return out


def classify(p):
    hay = " ".join([p.get("name", ""), " ".join(p.get("categories", [])),
                    " ".join(p.get("keywords", []))]).lower()
    cat_hay = " ".join(p.get("categories", [])).lower() or hay
    if re.search(EXCLUDE, cat_hay):
        return []
    return [k for k, rx in TARGET.items() if re.search(rx, hay)]


# ---------------------------------------------------------------- main
def main():
    if not (PCNA_ID and PCNA_PW):
        print("PCNA_ID / PCNA_PASSWORD secrets missing")
        return 1
    os.makedirs(OUT, exist_ok=True)
    summary = ["# PCNA catalog pull", ""]

    body = ("<shar:wsVersion>2.0.0</shar:wsVersion>" + creds() + LOC +
            "<shar:isSellable>true</shar:isSellable>")
    s, raw = post(PD200, "getProductSellable", env("2.0.0", "GetProductSellableRequest", body), timeout=240)
    r = parse(raw)
    ids = []
    for ps in all_(r, "ProductSellable"):
        pid = first(ps, "productId")
        if pid and pid not in ids:
            ids.append(pid)
    summary.append(f"- Sellable styles: **{len(ids)}**")
    if not ids:
        summary.append(f"- FAILED: {err(r, raw)}")
        return finish(summary, 1)

    # Probe which GetProduct variant works.
    global PRODUCT_CALL
    probe = ids[:5]
    for label, fn in (("v2.0.0 @ psproductdata200", get_product_v2),
                      ("v1.0.0 @ psproductdata100", get_product_v1)):
        ok = 0
        for pid in probe:
            s, raw = fn(pid)
            if parse_product(parse(raw))["name"]:
                ok += 1
            else:
                last_err = err(parse(raw), raw)
        summary.append(f"- GetProduct {label}: {ok}/{len(probe)} OK"
                       + ("" if ok else f" ({last_err})"))
        if ok:
            PRODUCT_CALL = fn
            break
    if not PRODUCT_CALL:
        return finish(summary, 1)

    # Details for every product.
    products, failures = {}, []
    lock = threading.Lock()

    def detail(pid):
        s, raw = PRODUCT_CALL(pid)
        p = parse_product(parse(raw))
        p["id"] = pid
        return pid, p, (None if p["name"] else err(parse(raw), raw))

    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        for f in as_completed([ex.submit(detail, i) for i in ids]):
            pid, p, e = f.result()
            with lock:
                products[pid] = p
                if e:
                    failures.append(f"{pid}: {e}")
    summary.append(f"- Details: {len(ids) - len(failures)} OK, {len(failures)} failed "
                   f"({time.time() - t0:.0f}s)")

    # Classify + pricing for target categories.
    targets = []
    for pid, p in products.items():
        p["aps_groups"] = classify(p) if p["name"] else []
        if p["aps_groups"] and not p["closeout"]:
            targets.append(pid)

    def price(pid):
        s, raw = fob_points(pid)
        r = parse(raw)
        fobs = [(first(f, "fobId"), first(f, "fobPostalCode")) for f in all_(r, "FobPoint")]
        if not fobs:
            return pid, {"fob": None, "pricing_error": err(r, raw)}
        s, raw = list_pricing(pid, fobs[0][0])
        pr = parse_pricing(parse(raw))
        pr["fob"] = fobs[0][0]
        pr["fob_zip"] = fobs[0][1]
        pr["fob_count"] = len(fobs)
        return pid, pr

    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        for f in as_completed([ex.submit(price, i) for i in targets]):
            pid, pr = f.result()
            products[pid].update(pr)
    summary.append(f"- Priced (List/MSRP only) in target groups: {len(targets)} "
                   f"({time.time() - t0:.0f}s)")

    with open(os.path.join(OUT, "pcna-catalog.json"), "w", encoding="utf-8") as fh:
        json.dump(sorted(products.values(), key=lambda x: x["id"]), fh, indent=1)
    with open(os.path.join(OUT, "failures.txt"), "w") as fh:
        fh.write("\n".join(failures))

    # Category counts (no prices in the public summary).
    from collections import Counter
    g = Counter(x for pid in targets for x in products[pid]["aps_groups"])
    c = Counter(cat for p in products.values() for cat in p.get("categories", []))
    b = Counter(p.get("brand") or "-" for pid, p in products.items() if pid in targets)
    summary += ["", "## Target groups (non-closeout)", ""]
    summary += [f"- {k}: {v}" for k, v in g.most_common()]
    summary += ["", "## Top PCNA categories (all products)", ""]
    summary += [f"- {k}: {v}" for k, v in c.most_common(40)]
    summary += ["", "## Brands in target groups", ""]
    summary += [f"- {k}: {v}" for k, v in b.most_common(30)]
    return finish(summary, 0)


def finish(lines, code):
    text = "\n".join(lines) + "\n"
    print(text)
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
