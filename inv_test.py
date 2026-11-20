"""Connection test: PromoStandards Inventory for Lane Seven + PCNA (counts only, no prices).
Finds each company's Inventory endpoint in the PromoStandards directory, then
asks for one sample product and prints the shape of the answer."""
import json, os, re, urllib.request, urllib.error, xml.etree.ElementTree as ET

DIR = "https://services.promostandards.org/WebServiceRepository/WebServiceRepository.svc/json"
SUP = {
  "lane7": {"id": os.environ.get("LANE7_ID",""), "pw": os.environ.get("LANE7_PASSWORD",""), "match": r"lane\s*seven|lanes?even",
            "sample": "LS14001", "guess": ["https://promostandards.lanesevenapparel.com/inventory.php",
                                            "https://promostandards.lanesevenapparel.com/inventoryService.php"]},
  "pcna":  {"id": os.environ.get("PCNA_ID",""), "pw": os.environ.get("PCNA_PASSWORD",""), "match": r"pcna|polyconcept|leed|bullet",
            "sample": os.environ.get("PCNA_SAMPLE","SM-6566"), "guess": ["https://psinventory200.pcna.online", "https://psinventory121.pcna.online"]},
}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept":"application/json"}), timeout=60) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print("  dir error", url, e); return None
def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def soap(url, ver, sup, pid):
    ns = f'xmlns:ns="http://www.promostandards.org/WSDL/Inventory/{ver}/" xmlns:shar="http://www.promostandards.org/WSDL/Inventory/{ver}/SharedObjects/"'
    if ver == "2.0.0":
        body = f"<shar:wsVersion>2.0.0</shar:wsVersion><shar:id>{esc(sup['id'])}</shar:id><shar:password>{esc(sup['pw'])}</shar:password><shar:productId>{esc(pid)}</shar:productId>"
    else:
        body = f"<ns:wsVersion>1.2.1</ns:wsVersion><ns:id>{esc(sup['id'])}</ns:id><ns:password>{esc(sup['pw'])}</ns:password><ns:productID>{esc(pid)}</ns:productID>"
    x = (f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" {ns}><soapenv:Header/><soapenv:Body>'
         f'<ns:GetInventoryLevelsRequest>{body}</ns:GetInventoryLevelsRequest></soapenv:Body></soapenv:Envelope>')
    req = urllib.request.Request(url, data=x.encode(), method="POST", headers={"Content-Type":"text/xml; charset=utf-8","SOAPAction":"getInventoryLevels"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r: return r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: return e.code, e.read().decode("utf-8","replace")
    except Exception as e: return 0, f"{type(e).__name__}: {e}"
L = lambda t: t.rsplit("}",1)[-1]
def summarize(raw):
    try: root = ET.fromstring(raw)
    except Exception: print("    not XML:", raw[:300].replace("\n"," ")); return
    parts = [e for e in root.iter() if L(e.tag) in ("PartInventory","ProductVariationInventory")]
    errs = [e.text for e in root.iter() if L(e.tag) in ("description","faultstring") and e.text]
    print(f"    parts: {len(parts)}  errors: {errs[:2]}")
    for p in parts[:6]:
        d = {}
        for c in p.iter():
            n = L(c.tag)
            if n in ("partId","partID","partColor","labelSize","partDescription","mainPart","value","quantityAvailable","manufacturedItem","buyToOrder") and c.text and c.text.strip():
                d.setdefault(n, c.text.strip())
        print("     ", d)
    tags = sorted({L(e.tag) for e in root.iter()})
    print("    tags:", ", ".join(tags)[:900])
comps = get(DIR + "/companies") or []
for key, sup in SUP.items():
    print(f"=== {key}: creds {'set' if sup['id'] and sup['pw'] else 'MISSING'}")
    urls = []
    for c in comps:
        name = c.get("Name") or c.get("name") or ""
        if re.search(sup["match"], name, re.I):
            code = c.get("Code") or c.get("code")
            print("  directory:", name, code)
            eps = get(f"{DIR}/companies/{code}/endpoints") or []
            for ep in eps:
                svc = ep.get("Service") or {}
                st = (svc.get("ServiceType") or {}).get("Code") if isinstance(svc.get("ServiceType"), dict) else svc.get("ServiceType")
                s = json.dumps(ep)
                if "INV" in s.upper():
                    url = (ep.get("URL") or ep.get("Url") or "")
                    ver = svc.get("Version") or ""
                    print("   inventory endpoint:", url, ver, (ep.get("Status") or ""))
                    if url: urls.append((url, ver))
    for g in sup["guess"]:
        urls.append((g, "2.0.0" if "200" in g or "inventory.php" in g else "1.2.1"))
    seen = set()
    for url, ver in urls:
        for v in ([ver] if ver in ("2.0.0","1.2.1") else ["2.0.0","1.2.1"]):
            if (url, v) in seen: continue
            seen.add((url, v))
            code, raw = soap(url, v, sup, sup["sample"])
            print(f"  {url} v{v} -> HTTP {code}, {len(raw)} bytes")
            if code == 200: summarize(raw)
            else: print("    ", raw[:250].replace("\n"," "))
