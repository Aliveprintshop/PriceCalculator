"""Otto Cap API connection test. Manual only. Prints status codes and counts, never prices or secrets."""
import base64, json, os, urllib.parse, urllib.request

U, P = os.environ.get('OTTO_USER', ''), os.environ.get('OTTO_PASSWORD', '')
CID, CS = os.environ.get('OTTO_CLIENT_ID', ''), os.environ.get('OTTO_CLIENT_SECRET', '')
SUPPLIER = '00ceb24d-9b6f-4ba1-91c8-aa375ab96651'
HOSTS = {'sandbox': 'https://sandbox-api.ottocap.com', 'live': 'https://connectivity.ottocap.com'}
SLUGS = {
    '31-069': '31-069-5-panel-mid-profile-baseball-cap',
    '116': '116-otto-capr-club-collection-5-panel-mid-profile-perforated-cap',
    '113': '113-otto-capr-club-collection-6-panel-pro-style-perforated-cap',
    '120': '120-otto-capr-club-collection-5-panel-mid-profile-perforated-cap',
    '18-202': '18-202-6-panel-low-profile-dad-hat',
    '39-165': '39-165-5-panel-high-crown-mesh-back-trucker-hat',
}
UA = {'User-Agent': 'Mozilla/5.0 AlivePrintShop-sync'}

def req(url, data=None, headers=None, method=None):
    r = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=40) as f:
            return f.status, f.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()

print('secrets present:', {k: bool(v) for k, v in [('user', U), ('password', P), ('client_id', CID), ('client_secret', CS)]})

# sample SKUs from Otto's public catalog
samples = {}
for st, slug in SLUGS.items():
    s, b = req(f'https://ottocap.com/api/s/catalog/search/{slug}?lookup_field=slug')
    if s != 200:
        print(st, 'public catalog', s); continue
    d = json.loads(b)
    act = [v['sku'] for v in d.get('varients', []) if v.get('status') == 'active' and '.' not in v['sku'].split('-')[0]]
    samples[st] = act[:2]
    print(st, 'public catalog OK, active SKUs:', len(act), 'sample:', act[:2])

basic = base64.b64encode(f'{CID}:{CS}'.encode()).decode()
for env, host in HOSTS.items():
    body = urllib.parse.urlencode({'username': U, 'password': P, 'grant_type': 'password'}).encode()
    s, b = req(host + '/authenticate/token/', body, {'Authorization': 'Basic ' + basic, 'Content-Type': 'application/x-www-form-urlencoded'}, 'POST')
    tok = None
    try:
        tok = json.loads(b).get('access_token')
    except Exception:
        pass
    print(f'[{env}] token: HTTP {s}, token received: {bool(tok)}', '' if tok else '| ' + b[:160].decode('utf-8', 'replace').replace(U, '<user>'))
    if not tok:
        continue
    H = {'Authorization': 'Bearer ' + tok}
    for st, skus in samples.items():
        for sku in skus:
            s, b = req(host + '/inventory?' + urllib.parse.urlencode({'sku': sku, 'supplier': SUPPLIER}), headers=H)
            try:
                d = json.loads(b)
                print(f'  [{env}] {sku}: HTTP {s}, stock {d.get("total_stock")}, warehouses {len(d.get("warehouse_stock") or [])}, price tiers {len(d.get("latest_price") or [])}, has MAP {d.get("map_price") is not None}')
            except Exception:
                print(f'  [{env}] {sku}: HTTP {s}', b[:120])
