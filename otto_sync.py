#!/usr/bin/env python3
"""Build otto-products.json from OTTO CAP's public catalog (ottocap.com).

Austin's picks (2026-11-24). Pricing: Otto's public price is the blank cost basis (x 1.5 happens on the site,
same as SanMar). Adult one-size colors only. Decoration methods are fixed per style (deco_methods).
Run weekly by .github/workflows/otto-sync.yml; merged into products.json by sync.yml (merge-pcna.py).
"""
import io, json, os, re, sys, time, urllib.request
from html import unescape

STYLES = [
    # style, slug on ottocap.com, decoration methods, subcategory
    ('31-069', '31-069-5-panel-mid-profile-baseball-cap', ['em'], 'Baseball Caps'),
    ('116', '116-otto-capr-club-collection-5-panel-mid-profile-perforated-cap', ['em'], 'Performance Caps'),
    ('113', '113-otto-capr-club-collection-6-panel-pro-style-perforated-cap', ['em'], 'Performance Caps'),
    ('120', '120-otto-capr-club-collection-5-panel-mid-profile-perforated-cap', ['em'], 'Performance Caps'),
    ('18-202', '18-202-6-panel-low-profile-dad-hat', ['em'], 'Dad Hats'),
    ('39-165', '39-165-5-panel-high-crown-mesh-back-trucker-hat', ['em', 'ht'], 'Trucker Caps'),
]
UA = {'User-Agent': 'Mozilla/5.0 (AlivePrintShop catalog sync)'}

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as f:
                return f.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3)

try:
    from PIL import Image
except Exception:
    Image = None

_hexcache = {}
def swatch_hex(url):
    if not url or Image is None:
        return '#888888'
    if url in _hexcache:
        return _hexcache[url]
    h = '#888888'
    try:
        im = Image.open(io.BytesIO(get(url))).convert('RGB')
        w, ht = im.size
        # lower-right quarter: on split swatches this is the second (main) color, like SanMar's hex
        box = im.crop((w // 2, ht // 2, w * 7 // 8, ht * 7 // 8)).resize((1, 1), Image.BILINEAR)
        r, g, b = box.getpixel((0, 0))
        h = '#%02X%02X%02X' % (r, g, b)
    except Exception as e:
        print('  swatch failed', url[-40:], e)
    _hexcache[url] = h
    return h

def clean_html(s):
    s = re.sub(r'<br\s*/?>|</p>|</li>', '\n', s or '', flags=re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = unescape(s)
    lines = [re.sub(r'\s+', ' ', l).strip() for l in s.split('\n')]
    lines = [l for l in lines if l and not l.startswith('*')]  # drop Otto's running-change notices
    return ' '.join(lines)[:900]

def img(images, kind):
    for i in images or []:
        if i.get('type') == kind:
            return i.get('medium') or i.get('large')
    return None

def build(style, slug, methods, sub):
    d = json.loads(get(f'https://ottocap.com/api/s/catalog/search/{slug}?lookup_field=slug'))
    price = d.get('customer_price')
    try:
        price = round(float(price), 2)
    except Exception:
        print(f'::warning::{style}: no public price, skipped'); return None
    cols, seen, skipped = [], set(), 0
    for v in d.get('varients') or []:
        a = v.get('attr') or {}
        if v.get('status') != 'active' or re.match(r'^\d+\.', v.get('sku', '')):
            continue  # inactive, or a case-pack duplicate SKU (90.xxx)
        size = ((a.get('otto_size') or {}).get('swatch_text') or '')
        if size and ('adult' not in size.lower() or 'young' in size.lower()):
            continue  # adult one-size only
        c = a.get('otto_color') or {}
        txt = c.get('swatch_text') or ''
        code, _, name = txt.partition(' - ')
        code, name = code.strip(), (name or txt).strip()
        if not code or code in seen:
            continue
        if not re.fullmatch(r'\d+', code):
            skipped += 1; continue  # pattern / special print codes (e.g. 021CPB21)
        seen.add(code)
        ims = v.get('images') or []
        front, back = img(ims, 'F'), img(ims, 'B')
        if not front:
            continue
        gallery = [x for x in (img(ims, 'FB'), img(ims, 'I')) if x]
        cols.append({'name': name, 'code': code, 'hex': swatch_hex(c.get('swatch')),
                     'otto_sku': v.get('sku'),
                     'images': {'front_flat': front, 'back_flat': back, 'front_model': front, 'back_model': back,
                                'side_model': None, 'gallery': gallery}})
    cols.sort(key=lambda c: (len(c['code']) > 3, c['code']))
    title = re.sub(r'\s+', ' ', (d.get('title') or '').replace('®', '').replace('OTTO CAP', '')).strip()
    print(f'{style}: {len(cols)} colors, {skipped} pattern colors skipped, methods {methods}')
    return {
        'style': style, 'name': f'OTTO CAP {title} {style}', 'brand': 'OTTO CAP', 'category': 'Caps',
        'subcategory': sub, 'description': clean_html(d.get('description')),
        'case_price': price, 'case_sale_price': None, 'sale_start_date': None, 'sale_end_date': None,
        'msrp': None, 'piece_weight_lbs': 0.2, 'product_status': 'Regular', 'discontinued': False,
        'available_sizes': ['OSFA'], 'size_upcharges': {}, 'deco_methods': methods,
        'source': 'otto', 'colors': cols,
    }

def logo():
    out = 'media/brands/otto-cap.png'
    if os.path.exists(out) or Image is None:
        return
    try:
        im = Image.open(io.BytesIO(get('https://ottocap.com/assets/images/common/logo.png'))).convert('RGBA')
        bg = Image.new('RGBA', im.size, (255, 255, 255, 0))
        px = im.load()
        # trim near-white / transparent edges
        bbox = Image.eval(im.convert('L'), lambda v: 255 if v < 235 else 0).getbbox()
        a = im.split()[3].getbbox()
        box = bbox if bbox else a
        if box:
            im = im.crop(box)
        h = 120
        im = im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)
        os.makedirs('media/brands', exist_ok=True)
        im.save(out)
        print('saved', out, im.size)
    except Exception as e:
        print('::warning::logo failed', e)

def main():
    rows = [p for p in (build(*s) for s in STYLES) if p]
    if len(rows) < len(STYLES) // 2:
        print('::error::too few Otto styles built; keeping the old file'); return 1
    json.dump({'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'source': 'OTTO CAP public catalog',
               'product_count': len(rows), 'products': rows}, open('otto-products.json', 'w'), indent=1, ensure_ascii=False)
    logo()
    print('wrote otto-products.json with', len(rows), 'styles')
    return 0

if __name__ == '__main__':
    sys.exit(main())
