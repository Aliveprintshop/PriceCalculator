"""Audit bag photo crops: does the stored crop box cut part of the product off?
Writes audit/bag-crops.json and contact sheets audit/bag-crops-N.jpg
(red = stored box, green = full product extent)."""
import io, json, sys, urllib.request, concurrent.futures as cf
import numpy as np
from PIL import Image, ImageDraw

prods = json.load(open("products.json"))["products"]
bags = [p for p in prods if str(p.get("category", "")).lower().startswith("bag")]
SIDES = (("f", "front_flat"), ("b", "back_flat"))
jobs = []
for p in bags:
    for c in p.get("colors") or []:
        for side, key in SIDES:
            u = (c.get("images") or {}).get(key)
            b = (c.get("crop") or {}).get(side)
            if u and b:
                jobs.append((p["style"], c["name"], side, u, b))
print("bag views with a crop:", len(jobs), "styles:", len(bags))

def full_box(im):
    W, H = im.size
    g = np.asarray(im.convert("L")).astype(int)
    h, w = g.shape
    bg = np.median(np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]]))
    m = (g < 246) | (abs(g - bg) > 9)
    rows = np.where(m.sum(1) >= max(2, int(0.002 * w)))[0]
    cols = np.where(m.sum(0) >= max(2, int(0.002 * h)))[0]
    if not len(rows) or not len(cols):
        return None
    return [cols[0] / w, rows[0] / h, (cols[-1] + 1) / w, (rows[-1] + 1) / h]

def one(j):
    st, col, side, u, b = j
    try:
        raw = urllib.request.urlopen(u, timeout=40).read()
        im = Image.open(io.BytesIO(raw)); im.draft("L", (im.size[0] // 3, im.size[1] // 3)); im = im.convert("RGB")
        fb = full_box(im)
    except Exception as e:
        return dict(style=st, color=col, side=side, url=u, err=str(e))
    if not fb:
        return dict(style=st, color=col, side=side, url=u, err="no product found")
    cb = [v / 1000 for v in b[:4]]
    cut = {"left": cb[0] - fb[0], "top": cb[1] - fb[1], "right": fb[2] - cb[2], "bottom": fb[3] - cb[3]}
    worst = max(cut.values())
    return dict(style=st, color=col, side=side, url=u, crop=b, full=[round(v * 1000) for v in fb] + [b[4]],
                cut={k: round(v, 3) for k, v in cut.items()}, worst=round(worst, 3), _im=im if worst > 0.015 else None)

with cf.ThreadPoolExecutor(16) as ex:
    res = list(ex.map(one, jobs))
bad = sorted([r for r in res if r.get("worst", 0) > 0.015], key=lambda r: -r["worst"])
errs = [r for r in res if r.get("err")]
print("cut off (>1.5%):", len(bad), "styles:", len({r["style"] for r in bad}), "errors:", len(errs))
import os
os.makedirs("audit", exist_ok=True)
json.dump({"checked": len(res), "bad": [{k: v for k, v in r.items() if k != "_im"} for r in bad],
           "errors": errs[:50]}, open("audit/bag-crops.json", "w"), indent=1)
# contact sheets, one tile per style (worst view), 24 per sheet
seen, tiles = set(), []
for r in bad:
    if r["style"] in seen: continue
    seen.add(r["style"]); tiles.append(r)
T = 260
for s in range(0, len(tiles), 24):
    chunk = tiles[s:s + 24]
    sheet = Image.new("RGB", (6 * T, ((len(chunk) + 5) // 6) * (T + 30)), "white")
    d = ImageDraw.Draw(sheet)
    for i, r in enumerate(chunk):
        im = r["_im"]; im.thumbnail((T - 10, T - 10))
        x, y = (i % 6) * T + 5, (i // 6) * (T + 30) + 5
        sheet.paste(im, (x, y))
        w, h = im.size
        for box, colr in ((r["crop"], (220, 30, 30)), (r["full"], (20, 170, 60))):
            bx = [box[0] / 1000 * w + x, box[1] / 1000 * h + y, box[2] / 1000 * w + x, box[3] / 1000 * h + y]
            d.rectangle(bx, outline=colr, width=2)
        d.text((x, y + h + 2), f"{r['style']} {r['color'][:14]} {r['side']} {r['worst']:.2f}", fill=(0, 0, 0))
    sheet.save(f"audit/bag-crops-{s // 24 + 1}.jpg", quality=82)
print("sheets:", (len(tiles) + 23) // 24)
