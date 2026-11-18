#!/usr/bin/env python3
"""Merge a vendor file (pcna-products.json, lane7-products.json) into products.json (in place).

Run after the SanMar sync (which rewrites products.json from scratch) so the
PCNA promo products ride along in the one catalog every page and the checkout
Worker already read. Safe to run more than once: old PCNA entries are removed
before the current ones are added.

Usage: python merge-pcna.py [products.json] [pcna-products.json]
"""
import json, sys, os

def main(cat_path='products.json', pcna_path='pcna-products.json'):
    if not os.path.exists(pcna_path):
        print(f'{pcna_path} not found - nothing to merge')
        return 0
    cat = json.load(open(cat_path, encoding='utf-8'))
    rows = cat['products'] if isinstance(cat, dict) else cat
    pcna = json.load(open(pcna_path, encoding='utf-8'))
    add = pcna.get('products') or []

    srcs = {p.get('source') for p in add if p.get('source')} or {'pcna'}
    kept = [p for p in rows if p.get('source') not in srcs]
    taken = {str(p.get('style', '')).upper() for p in kept}
    merged, clashes = [], []
    for p in add:
        if str(p.get('style', '')).upper() in taken:
            clashes.append(p.get('style'))
            continue
        merged.append(p)
    out = kept + merged
    if isinstance(cat, dict):
        cat['products'] = out
        cat['product_count'] = len(out)
    else:
        cat = out
    with open(cat_path, 'w', encoding='utf-8') as f:
        json.dump(cat, f, indent=2, ensure_ascii=False)
    print(f'merged {len(merged)} {"/".join(sorted(srcs))} entries into {cat_path} ({len(out)} total)')
    if clashes:
        print(f'::warning::skipped {len(clashes)} {"/".join(sorted(srcs))} styles that clash with SanMar: {clashes}')
    return 0

if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
