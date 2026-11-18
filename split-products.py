#!/usr/bin/env python3
"""Split products.json into one small file per style for the product page.

  _site/p/<KEY>.json   = {"product": {...}}   (KEY = style upper-cased, [^A-Z0-9_-] -> _)
  _site/p/_colors.json = {"color name": "#hex"}  catalog-wide swatch hex map, built with the
                         same rule as buildHexLookup(): first product that names a colour wins.

The product page loads only these two small files instead of the whole 17 MB catalog.
Usage: python tools/split_products.py products.json _site/p
"""
import json, os, re, sys
from decimal import Decimal, ROUND_HALF_UP

# ---- search-index.json: the header search bar on aliveprintshop.com -------------
# (site-search.js). One small row per product the /products/ grid lists, with the
# same exclusions and the same "from" price as the browse cards in index.html.
# Keep in sync with loadProducts()/computeFromPrice() there.
EXCLUDE_NAME = re.compile(r"\b(socks?|gloves?|mittens?)\b", re.I)
EXCLUDE_STYLES = {'CTA202', 'CTA207', 'CTA267', 'CT104485', 'CS820', 'CS800', 'LACE'}
EXCLUDE_NAME_EXACT = {'trucker hat - local supplier'}
BUCKETS = [('T-Shirts', ['T-Shirts']), ('Activewear', ['Activewear']),
           ('Sweatshirts & Hoodies', ['Sweatshirts/Fleece']),
           ('Polos & Button-Downs', ['Polos/Knits', 'Woven Shirts']), ('Outerwear', ['Outerwear']),
           ('Headwear', ['Caps']), ('Bags', ['Bags']), ('Drinkware', ['Drinkware']),
           ('Journals & Notebooks', ['Journals & Notebooks']), ('Pens', ['Pens']),
           ('Technology', ['Technology']), ('Keychains', ['Keychains']),
           ('Workwear & Safety', ['Workwear', 'Personal Protection']), ('Bottoms', ['Bottoms']),
           ('Women', ["Women's"]), ('Youth', ['Youth']), ('Toddler', ['Infant & Toddler']),
           ('Specialty', ['Tall', 'Accessories'])]


def _bucket(p):
    n = (p.get('name') or '').lower()
    if 'long sleeve' in n:
        return 'Long Sleeve'
    if re.search(r'\btank\b', n):
        return 'Tank Tops'
    for label, cats in BUCKETS:
        if p.get('category') in cats:
            return label
    return ''


def _fixed2(x):
    """JavaScript's x.toFixed(2): half-up on the exact binary value."""
    return float(Decimal(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _embroidered(cat):
    c = (cat or '').lower()
    return any(k in c for k in ('cap', 'polo', 'knit', 'woven', 'outerwear', 'bag'))


def _from_price(p):
    if p.get('_pcna') or p.get('_drinkware'):
        vals = [v for row in (p.get('_dwMatrix') or {}).values() for v in row.values()
                if isinstance(v, (int, float))]
        return _fixed2(min(vals)) if vals else None
    base = p.get('case_sale_price') if p.get('case_sale_price') is not None else p.get('case_price')
    if base is None:
        return None
    unit = _fixed2(base * 1.5)
    return _fixed2(unit + (5.00 + 45.0 / 144 if _embroidered(p.get('category')) else 2.60))


def search_row(p):
    if not p or not p.get('style') or p.get('discontinued') is True or p.get('_hidden'):
        return None
    name = p.get('name') or ''
    if EXCLUDE_NAME.search(name) or str(p['style']).upper() in EXCLUDE_STYLES \
            or name.lower().strip() in EXCLUDE_NAME_EXACT:
        return None
    price = _from_price(p)
    if price is None:
        return None
    cols = p.get('colors') or []
    im = (cols[0].get('images') or {}) if cols else {}
    seen, names = set(), []
    for c in cols:
        nm = (c.get('name') or '').strip()
        if nm and nm.lower() not in seen:
            seen.add(nm.lower())
            names.append(nm)
    return {'s': str(p['style']), 'n': name, 'b': p.get('brand') or '',
            'c': ' '.join(x for x in (p.get('category'), p.get('subcategory'), _bucket(p)) if x),
            'k': ' '.join(names), 'd': (p.get('description') or '')[:220],
            'p': price, 'i': im.get('front_flat') or im.get('front_model') or ''}

def key(style):
    return re.sub(r'[^A-Z0-9_-]', '_', str(style).strip().upper())

def main(src, out):
    data = json.load(open(src, encoding='utf-8'))
    rows = data if isinstance(data, list) else (data.get('products') or [])
    os.makedirs(out, exist_ok=True)
    hexmap, seen, n = {}, set(), 0
    for p in rows:
        for c in p.get('colors') or []:
            name, hx = c.get('name'), c.get('hex')
            if name and hx and hx != '#888888' and '/' not in name:
                hexmap.setdefault(name.lower(), hx)
        k = key(p.get('style', ''))
        if not k or k in seen:
            continue
        seen.add(k)
        with open(os.path.join(out, k + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'product': p}, f, separators=(',', ':'))
        n += 1
    with open(os.path.join(out, '_colors.json'), 'w', encoding='utf-8') as f:
        json.dump(hexmap, f, separators=(',', ':'))
    # Header search index, one level up from p/ (i.e. _site/search-index.json).
    try:
        rows_s, seen_s = [], set()
        for p in rows:
            r = search_row(p)
            if r and r['s'].upper() not in seen_s:
                seen_s.add(r['s'].upper())
                rows_s.append(r)
        with open(os.path.join(os.path.dirname(os.path.abspath(out)), 'search-index.json'),
                  'w', encoding='utf-8') as f:
            json.dump({'v': 1, 'items': rows_s}, f, separators=(',', ':'), ensure_ascii=False)
        print('wrote search-index.json (%d products)' % len(rows_s))
    except Exception as e:
        print('::warning::search-index.json not written: %s' % e)
    print('wrote %d product files + _colors.json (%d colours) to %s' % (n, len(hexmap), out))

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'products.json', sys.argv[2] if len(sys.argv) > 2 else '_site/p')
