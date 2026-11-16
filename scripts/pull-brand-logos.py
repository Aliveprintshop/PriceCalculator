"""One-off: pull SanMar brand logos into media/brands/.

Downloads SanMar_SDL_N.csv over SFTP (same login as the nightly sync), reads
the BRAND_LOGO_IMAGE column for every brand we carry (brands in products.json),
fetches each logo and writes:
  media/brands/<slug>.<ext>      the logo file
  media/brands/brands.json       [{brand, slug, file, source, products}]
Run from the "Pull SanMar brand logos" workflow (workflow_dispatch only).
"""
import csv, collections, urllib.parse, importlib.util, json, os, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sync", ROOT / "sync-sanmar.py")
sync = importlib.util.module_from_spec(spec); spec.loader.exec_module(sync)

OUT = ROOT / "media" / "brands"; OUT.mkdir(parents=True, exist_ok=True)
tmp = Path("/tmp/sanmar"); tmp.mkdir(exist_ok=True)
sdl, _ = sync.download_sanmar_files(tmp)

carried = collections.Counter(p["brand"] for p in json.load(open(ROOT / "products.json"))["products"])
csv.field_size_limit(sys.maxsize)
logos = collections.defaultdict(collections.Counter)
with open(sdl, encoding="latin-1", newline="") as f:
    r = csv.DictReader(f)
    print("COLUMNS:", r.fieldnames)
    for row in r:
        b = (row.get("MILL") or "").strip()
        v = (row.get("BRAND_LOGO_IMAGE") or "").strip()
        if b and v: logos[b][v] += 1
print("BRANDS WITH LOGO VALUES:", len(logos))
for b, c in sorted(logos.items()): print(f"  {b!r}: {c.most_common(3)}")

def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
CANDIDATES = ["{v}", "https://cdnm.sanmar.com/catalog/images/{v}", "https://cdnm.sanmar.com/brandlogos/{v}",
              "https://cdnm.sanmar.com/imglib/brandlogos/{v}", "https://www.sanmar.com/medias/{v}"]
def fetch(v):
    for t in CANDIDATES:
        u = t.format(v=urllib.parse.quote(v))
        if not u.startswith("http"): continue
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read(); ct = resp.headers.get("Content-Type", "")
                if resp.status == 200 and ("image" in ct or data[:4] in (b"\x89PNG", b"GIF8") or data[:2] == b"\xff\xd8" or b"<svg" in data[:300]):
                    return u, data, ct
        except Exception as e:
            print("    miss", u, type(e).__name__)
    return None, None, None

def trim(path, pad=4):
    """Cut SanMar's white padding so every logo fills its menu tile evenly."""
    try:
        from PIL import Image, ImageChops
        im = Image.open(path); rgb = im.convert("RGB")
        diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255))).convert("L").point(lambda v: 255 if v > 18 else 0)
        box = diff.getbbox()
        if not box: return
        l, t, r, b = box
        box = (max(0, l - pad), max(0, t - pad), min(im.width, r + pad), min(im.height, b + pad))
        out = im.crop(box)
        if str(path).endswith(".jpg"): out.convert("RGB").save(path, quality=92)
        else: out.save(path)
    except Exception as e:
        print("    trim failed", path, e)

index = []
for brand, n in carried.most_common():
    v = logos[brand].most_common(1)[0][0] if logos.get(brand) else ""
    entry = {"brand": brand, "slug": slug(brand), "products": n, "sanmar_value": v, "file": None, "source": None}
    if v:
        u, data, ct = fetch(v)
        if data:
            ext = (os.path.splitext(u.split("?")[0])[1] or ".jpg").lower()
            fn = entry["slug"] + ext
            # SanMar sends a blank all-white file for a few brands; skip those.
            try:
                from PIL import Image; import io
                if Image.open(io.BytesIO(data)).convert("L").getextrema()[0] >= 250:
                    print("    blank logo, skipped", u); data = None
            except Exception: pass
        if data:
            (OUT / fn).write_bytes(data)
            trim(OUT / fn)
            entry.update(file="media/brands/" + fn, source=u)
    print("BRAND", brand, "->", entry["file"] or "NO LOGO", "|", v)
    index.append(entry)
(OUT / "brands.json").write_text(json.dumps(index, indent=2))
print("done:", sum(1 for e in index if e["file"]), "of", len(index), "logos saved")
