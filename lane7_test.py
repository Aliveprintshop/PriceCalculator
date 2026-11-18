#!/usr/bin/env python3
"""
Lane Seven Apparel PromoStandards connection test.

Runs in GitHub Actions. Reads credentials from the LANE7_ID and LANE7_PASSWORD
environment variables (GitHub Secrets) -- never hard-code them here.

What it does
  1. Fetches the public WSDLs and checks the login on Lane Seven's Live endpoints
  2. Pulls the sellable product list (count + first IDs).
  3. For a few sample products: details, FOB point, pricing (List / Net /
     Customer, Decorated + Blank), and images.
  4. Writes a short public summary (status, counts, coded-markup ratios) to the
     Actions run summary, and the raw XML to lane7-out/ (uploaded as a private,
     1-day artifact).

Standard library only, so the workflow needs no pip install.
"""
import os
import re
import sys
import json
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

L7_ID = os.environ.get("LANE7_ID", "").strip()
L7_PW = os.environ.get("LANE7_PASSWORD", "").strip()
OUT = os.environ.get("LANE7_OUT", "lane7-out")
SAMPLES = [s.strip() for s in os.environ.get("LANE7_SAMPLES", "").split(",") if s.strip()]

# From Lane Seven's "Promostandard Endpoints" sheet (all Live).
BASE = "https://promostandards.lanesevenapparel.com"
URL = {
    "product":   BASE + "/productData.php",
    "pricing":   BASE + "/productPricingAndConfig.php",
    "media":     BASE + "/mediaContent.php",
    "inventory": BASE + "/inventory2.php",
}
WSDL = {
    "product":   BASE + "/wsdl/ProductDataService.wsdl",
    "pricing":   BASE + "/wsdl/PricingAndConfiguration.wsdl",
    "media":     BASE + "/wsdl/MediaContentService.wsdl",
    "inventory": BASE + "/wsdl/inventory2.0.0RC4/InventoryService.wsdl",
}

NS_PD = ('xmlns:ns="http://www.promostandards.org/WSDL/ProductDataService/2.0.0/" '
         'xmlns:shar="http://www.promostandards.org/WSDL/ProductDataService/2.0.0/SharedObjects/"')
NS_PPC = ('xmlns:ns="http://www.promostandards.org/WSDL/PricingAndConfiguration/1.0.0/" '
          'xmlns:shar="http://www.promostandards.org/WSDL/PricingAndConfiguration/1.0.0/SharedObjects/"')
NS_MED = ('xmlns:ns="http://www.promostandards.org/WSDL/MediaService/1.0.0/" '
          'xmlns:shar="http://www.promostandards.org/WSDL/MediaService/1.0.0/SharedObjects/"')
NS_INV = ('xmlns:ns="http://www.promostandards.org/WSDL/Inventory/2.0.0/" '
          'xmlns:shar="http://www.promostandards.org/WSDL/Inventory/2.0.0/SharedObjects/"')


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def envelope(ns, op, body):
    return ('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'{ns}><soapenv:Header/><soapenv:Body><ns:{op}>{body}</ns:{op}>'
            '</soapenv:Body></soapenv:Envelope>')


def creds():
    return f"<shar:id>{esc(L7_ID)}</shar:id><shar:password>{esc(L7_PW)}</shar:password>"


def req_sellable():
    return "getProductSellable", envelope(NS_PD, "GetProductSellableRequest",
        "<shar:wsVersion>2.0.0</shar:wsVersion>" + creds() +
        "<shar:localizationCountry>US</shar:localizationCountry>"
        "<shar:localizationLanguage>en</shar:localizationLanguage>"
        "<shar:isSellable>true</shar:isSellable>")


def req_product(pid):
    return "getProduct", envelope(NS_PD, "GetProductRequest",
        "<shar:wsVersion>2.0.0</shar:wsVersion>" + creds() +
        "<shar:localizationCountry>US</shar:localizationCountry>"
        "<shar:localizationLanguage>en</shar:localizationLanguage>"
        f"<shar:productId>{esc(pid)}</shar:productId>")


def req_fob(pid):
    return "getFobPoints", envelope(NS_PPC, "GetFobPointsRequest",
        "<shar:wsVersion>1.0.0</shar:wsVersion>" + creds() +
        f"<shar:productId>{esc(pid)}</shar:productId>"
        "<shar:localizationCountry>US</shar:localizationCountry>"
        "<shar:localizationLanguage>en</shar:localizationLanguage>")


def req_price(pid, fob, price_type, config_type):
    return "getConfigurationAndPricing", envelope(NS_PPC, "GetConfigurationAndPricingRequest",
        "<shar:wsVersion>1.0.0</shar:wsVersion>" + creds() +
        f"<shar:productId>{esc(pid)}</shar:productId>"
        "<shar:currency>USD</shar:currency>"
        f"<shar:fobId>{esc(fob)}</shar:fobId>"
        f"<shar:priceType>{price_type}</shar:priceType>"
        "<shar:localizationCountry>US</shar:localizationCountry>"
        "<shar:localizationLanguage>en</shar:localizationLanguage>"
        f"<shar:configurationType>{config_type}</shar:configurationType>")


def req_media(pid):
    return "getMediaContent", envelope(NS_MED, "GetMediaContentRequest",
        "<shar:wsVersion>1.1.0</shar:wsVersion>" + creds() +
        "<shar:cultureName>en-US</shar:cultureName>"
        "<shar:mediaType>Image</shar:mediaType>"
        f"<shar:productId>{esc(pid)}</shar:productId>")


def req_inventory(pid):
    return "getInventoryLevels", envelope(NS_INV, "GetInventoryLevelsRequest",
        "<shar:wsVersion>2.0.0</shar:wsVersion>" + creds() +
        f"<shar:productId>{esc(pid)}</shar:productId>")


def post(url, action, xml, timeout=90):
    data = xml.encode("utf-8")
    r = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": action,
    })
    t = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), time.time() - t
    except Exception as e:  # DNS, timeout, TLS
        return 0, f"{type(e).__name__}: {e}", time.time() - t


def get(url, timeout=30):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def local(tag):
    return tag.rsplit("}", 1)[-1]


def parse(xml):
    try:
        return ET.fromstring(xml)
    except ET.ParseError:
        return None


def find_all(root, name):
    return [e for e in root.iter() if local(e.tag) == name] if root is not None else []


def text(root, name):
    for e in find_all(root, name):
        if e.text and e.text.strip():
            return e.text.strip()
    return ""


def error_msg(root, raw):
    """PromoStandards errors come back as ErrorMessage/ServiceMessage or a SOAP Fault."""
    if root is None:
        return raw[:200].replace("\n", " ")
    for n in ("description", "faultstring", "Reason", "Text"):
        t = text(root, n)
        if t and ("error" in t.lower() or "auth" in t.lower() or "invalid" in t.lower()
                  or "not" in t.lower() or n == "faultstring"):
            code = text(root, "code")
            return (f"[{code}] " if code else "") + t
    return ""


def save(name, content):
    os.makedirs(OUT, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    with open(os.path.join(OUT, safe), "w", encoding="utf-8") as f:
        # Belt and braces: the password should never appear in a response, but scrub anyway.
        f.write(content.replace(L7_PW, "***") if L7_PW else content)


def price_table(root):
    """Return {partId: [(minQty, price), ...]} for the first configuration found."""
    out = {}
    for part in find_all(root, "Part"):
        pid = ""
        for c in part:
            if local(c.tag) == "partId" and c.text:
                pid = c.text.strip()
        rows = []
        for p in [e for e in part.iter() if local(e.tag) == "PartPrice"]:
            q = text(p, "minQuantity")
            v = text(p, "price")
            try:
                rows.append((int(float(q)), float(v)))
            except ValueError:
                pass
        if rows:
            out[pid or f"part{len(out)}"] = sorted(rows)
    return out


def charges(root):
    """Setup / run charges attached to decoration locations (Decorated config)."""
    out = []
    for ch in find_all(root, "Charge"):
        name = text(ch, "chargeName") or text(ch, "chargeDescription")
        ctype = text(ch, "chargeType")
        prices = []
        for cp in [e for e in ch.iter() if local(e.tag) == "ChargePrice"]:
            try:
                prices.append((int(float(text(cp, "xMinQty") or 0)), float(text(cp, "price") or 0)))
            except ValueError:
                pass
        out.append({"name": name, "type": ctype, "prices": sorted(set(prices))[:6]})
    # De-duplicate by name+type
    seen, uniq = set(), []
    for c in out:
        k = (c["name"], c["type"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


def decoration_methods(root):
    names = []
    for d in find_all(root, "Decoration"):
        n = text(d, "decorationName")
        if n and n not in names:
            names.append(n)
    return names


def main():
    lines = ["# Lane Seven connection test", ""]
    if not L7_ID or not L7_PW:
        lines.append("**FAILED:** LANE7_ID / LANE7_PASSWORD secrets are not set on the repo.")
        write_summary(lines)
        print("\n".join(lines))
        return 1

    # ---- 0. WSDLs (public; tell us the exact operations + namespaces) ------
    lines += ["## 0. WSDL check", "", "| Service | HTTP | Namespace |", "|---|---|---|"]
    for k, u in WSDL.items():
        ws, wraw = get(u)
        save(f"wsdl-{k}.xml", wraw)
        m = re.search(r'targetNamespace="([^"]+)"', wraw)
        lines.append(f"| {k} | {ws} | {m.group(1) if m else '-'} |")
    lines.append("")

    # ---- 1. Login check -------------------------------------------------------
    lines += ["## 1. Login check (GetProductSellable)", "",
              "| Endpoint | HTTP | Result | Time |", "|---|---|---|---|"]
    action, body = req_sellable()
    status, raw, dt = post(URL["product"], action, body, timeout=300)
    save("sellable.xml", raw)
    sellable_root = parse(raw)
    ids = find_all(sellable_root, "productId")
    result = (f"OK - {len({e.text for e in ids})} products" if ids
              else error_msg(sellable_root, raw) or "no products returned")
    lines += [f"| {URL['product']} | {status} | {result} | {dt:.1f}s |", ""]
    if not ids:
        lines.append("**Login or request failed.** Raw response and WSDLs are in the artifact.")
        write_summary(lines)
        print("\n".join(lines))
        return 1
    working_env = "live"
    url = URL

    # ---- 2. Sellable list -------------------------------------------------
    styles = []
    parts = 0
    for ps in find_all(sellable_root, "ProductSellable"):
        sid = text(ps, "productId")
        if sid and sid not in styles:
            styles.append(sid)
        if text(ps, "partId"):
            parts += 1
    if not styles:
        styles = sorted({e.text.strip() for e in find_all(sellable_root, "productId") if e.text})
    with open(os.path.join(OUT, "sellable-ids.json"), "w") as f:
        json.dump(styles, f)
    lines += [f"## 2. Sellable catalog ({working_env})", "",
              f"- Styles (product IDs): **{len(styles)}**",
              f"- Parts (SKUs): **{parts}**",
              f"- First 15: {', '.join(styles[:15])}", ""]

    samples = [s for s in SAMPLES if s in styles] or styles[:3]
    missing = [s for s in SAMPLES if s not in styles]
    if missing:
        lines.append(f"_Not in sellable list (skipped): {', '.join(missing)}_\n")

    # ---- 3. Per-sample detail -----------------------------------------------
    for pid in samples[:4]:
        lines += [f"## 3. Sample product {pid}", ""]
        a, b = req_product(pid)
        s, raw, _ = post(url["product"], a, b)
        save(f"{pid}-product.xml", raw)
        r = parse(raw)
        name = text(r, "productName")
        brand = text(r, "productBrand")
        cat = text(r, "category")
        colors = sorted({e.text.strip() for e in find_all(r, "colorName") if e.text})
        lines.append(f"- **GetProduct** HTTP {s}: {brand} {name} | category: {cat or '-'} | "
                     f"{len(colors)} colors" + ("" if name else f" | {error_msg(r, raw)}"))

        a, b = req_fob(pid)
        s, raw, _ = post(url["pricing"], a, b)
        save(f"{pid}-fob.xml", raw)
        r = parse(raw)
        fobs = [(text(f, "fobId"), text(f, "fobPostalCode") or text(f, "fobCity"))
                for f in find_all(r, "FobPoint")]
        lines.append(f"- **GetFobPoints** HTTP {s}: " +
                     (", ".join(f"{i} ({z})" for i, z in fobs) or error_msg(r, raw)))
        fob = fobs[0][0] if fobs else "1"

        tables = {}
        for cfg in ("Decorated", "Blank"):
            for pt in ("List", "Net", "Customer"):
                a, b = req_price(pid, fob, pt, cfg)
                s, raw, _ = post(url["pricing"], a, b)
                save(f"{pid}-price-{cfg}-{pt}.xml", raw)
                r = parse(raw)
                t = price_table(r)
                tables[(cfg, pt)] = t
                if cfg == "Decorated" and pt == "List":
                    meth = decoration_methods(r)
                    chg = charges(r)
                    lines.append(f"- **Decoration methods**: {', '.join(meth) or '-'}")
                    lines.append(f"- **Charges found**: " + ("; ".join(
                        f"{c['name']} ({c['type']})" for c in chg[:8]) or "-"))
                if not t:
                    lines.append(f"- Pricing {cfg}/{pt} HTTP {s}: no price rows "
                                 f"{error_msg(r, raw)}")

        # Coded-markup ratio: how much bigger List is than Net at each break.
        for cfg in ("Decorated", "Blank"):
            L, N, C = tables.get((cfg, "List"), {}), tables.get((cfg, "Net"), {}), tables.get((cfg, "Customer"), {})
            part = next(iter(L), None)
            if not part or part not in N:
                continue
            lines += ["", f"**{cfg} - markup of List over Net (part {part})**", "",
                      "| Min qty | List / Net | Discount off List | List / Customer |",
                      "|---|---|---|---|"]
            nmap = dict(N[part])
            cmap = dict(C.get(part, []))
            for q, lp in L[part]:
                np_ = nmap.get(q)
                cp = cmap.get(q)
                if np_:
                    lines.append(f"| {q} | {lp/np_:.3f}x | {(1-np_/lp)*100:.1f}% | "
                                 + (f"{lp/cp:.3f}x" if cp else "-") + " |")
        lines.append("")

        a, b = req_media(pid)
        s, raw, _ = post(url["media"], a, b)
        save(f"{pid}-media.xml", raw)
        r = parse(raw)
        urls = [e.text.strip() for e in find_all(r, "url") if e.text]
        lines.append(f"- **GetMediaContent** HTTP {s}: {len(urls)} images"
                     + (f" (e.g. {urls[0]})" if urls else f" {error_msg(r, raw)}"))

        a, b = req_inventory(pid)
        s, raw, _ = post(url["inventory"], a, b)
        save(f"{pid}-inventory.xml", raw)
        r = parse(raw)
        qty = find_all(r, "PartInventory")
        lines.append(f"- **GetInventoryLevels** HTTP {s}: {len(qty)} parts with inventory"
                     + ("" if qty else f" {error_msg(r, raw)}"))
        lines.append("")

    lines += ["---", "Raw XML is in the `lane7-raw` artifact on this run (kept 1 day)."]
    write_summary(lines)
    print("\n".join(lines))
    return 0


def write_summary(lines):
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
