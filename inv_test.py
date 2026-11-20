"""Connection test: Lane Seven Inventory 1.2.1 (counts only)."""
import os, re, urllib.request, urllib.error, xml.etree.ElementTree as ET
U = "https://promostandards.lanesevenapparel.com/inventory.php"
ID, PW = os.environ.get("LANE7_ID",""), os.environ.get("LANE7_PASSWORD","")
t = urllib.request.urlopen(U + "?wsdl", timeout=60).read().decode()
print(re.sub(r"\s+", " ", t)[:3600])
def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
NS = "http://www.promostandards.org/WSDL/InventoryService/1.0.0/"
for el in ("Request", "GetInventoryLevelsRequest"):
    x = (f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns="{NS}"><soapenv:Header/><soapenv:Body>'
         f'<ns:{el}><ns:wsVersion>1.2.1</ns:wsVersion><ns:id>{esc(ID)}</ns:id><ns:password>{esc(PW)}</ns:password><ns:productID>LS14001</ns:productID><ns:productIDtype>Supplier</ns:productIDtype></ns:{el}>'
         '</soapenv:Body></soapenv:Envelope>')
    req = urllib.request.Request(U, data=x.encode(), method="POST", headers={"Content-Type":"text/xml; charset=utf-8","SOAPAction":"getInventoryLevels"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r: code, raw = r.status, r.read().decode("utf-8","replace")
    except urllib.error.HTTPError as e: code, raw = e.code, e.read().decode("utf-8","replace")
    print(f"\n=== element {el}: HTTP {code}, {len(raw)} bytes")
    raw2 = re.sub(r"(<[^>]*[Pp]rice[^>]*>)[^<]*", r"\1#", raw)
    print(re.sub(r"\s+", " ", raw2)[:2500])
