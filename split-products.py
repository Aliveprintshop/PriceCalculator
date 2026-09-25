#!/usr/bin/env python3
"""Split products.json into one small file per style for the product page.

  _site/p/<KEY>.json   = {"product": {...}}   (KEY = style upper-cased, [^A-Z0-9_-] -> _)
  _site/p/_colors.json = {"color name": "#hex"}  catalog-wide swatch hex map, built with the
                         same rule as buildHexLookup(): first product that names a colour wins.

The product page loads only these two small files instead of the whole 17 MB catalog.
Usage: python tools/split_products.py products.json _site/p
"""
import json, os, re, sys

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
    print('wrote %d product files + _colors.json (%d colours) to %s' % (n, len(hexmap), out))

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'products.json', sys.argv[2] if len(sys.argv) > 2 else '_site/p')
