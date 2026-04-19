# Calculator patch: wire to live `products.json`

This patches `alive-pricing-calculator.html` to fetch product data from the GitHub Pages URL instead of using the hardcoded `ITEMS` array and `PROD_IMGS` object.

**Strategy:** minimal invasive change. We replace the hardcoded data with a fetch, then produce `ITEMS` / `PROD_IMGS` in the exact shape the existing calc code expects. The rich data (colors, sizes, upcharges, sale prices) is stashed in a parallel `ITEMS_BY_STYLE` lookup so future UI work can use it without breaking the current flow.

---

## Step 1 — Set your Pages URL

At the top of the script block (just after `<script>` on line 638), add one constant:

```js
const PRODUCTS_JSON_URL = 'https://YOUR_USERNAME.github.io/YOUR_REPO_NAME/products.json';
```

Replace with your actual Pages URL from the setup guide.

---

## Step 2 — Replace the hardcoded `ITEMS` array

Find this line (around line 640) — it starts with `const ITEMS=[{"s":"980",` and runs for several thousand characters:

```js
const ITEMS=[{"s":"980","n":"Gildan Softstyle Combed Ring Spun S/S Tee",...}];
```

**Delete the entire line** and replace with:

```js
let ITEMS = [];
let ITEMS_BY_STYLE = {};   // style → full product object (colors, sizes, etc.)
let PRODUCTS_META = {};    // { generated_at, markup_percent, turnaround, decoration_pricing }
```

---

## Step 3 — Replace `PROD_IMGS`

Find the line (around line 641) that starts with `const PROD_IMGS={"DM130":"data:image/jpeg;base64,...`. This is a very long one-liner.

**Delete the entire line** and replace with:

```js
let PROD_IMGS = {};  // style → first-color front image URL (populated from fetch)
```

---

## Step 4 — Add the fetch + bootstrap

Right **before** the `// -- INIT --` comment near the bottom (around line 1255), insert this block:

```js
// ============================================================================
//  LIVE DATA BOOTSTRAP
//  Fetches products.json from GitHub Pages, converts to the shape the
//  existing UI expects, then initializes the calculator.
// ============================================================================
async function loadProducts() {
  try {
    const resp = await fetch(PRODUCTS_JSON_URL, { cache: 'no-store' });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();

    PRODUCTS_META = {
      generated_at: data.generated_at,
      markup_percent: data.markup_percent,
      turnaround: data.turnaround,
      decoration_pricing: data.decoration_pricing,
    };

    const markupMult = 1 + (data.markup_percent / 100);

    ITEMS = data.products.map(p => {
      // Pick the effective blank case price: sale price if active, else case price
      const today = new Date().toISOString().slice(0, 10);
      const saleActive =
        p.case_sale_price != null &&
        (!p.sale_start_date || p.sale_start_date <= today) &&
        (!p.sale_end_date || p.sale_end_date >= today);
      const baseCasePrice = saleActive ? p.case_sale_price : p.case_price;
      const blankPerPiece = Math.round(baseCasePrice * markupMult * 100) / 100;

      // The legacy UI wants a simplified shape
      const simplified = {
        s: p.style,
        n: p.name || '',
        b: p.brand || '',
        c: p.category || '',
        p: blankPerPiece,
      };
      // Stash the full rich object for later use
      ITEMS_BY_STYLE[p.style] = p;

      // First color's front image → PROD_IMGS (legacy UI expects this as a string URL)
      const firstColor = (p.colors || [])[0];
      if (firstColor && firstColor.images) {
        const img = firstColor.images.front_model
          || firstColor.images.front_flat
          || firstColor.images.back_model
          || firstColor.images.back_flat;
        if (img) PROD_IMGS[p.style] = img;
      }

      return simplified;
    });

    // Rebuild the search index (IDX is built from ITEMS on page load above —
    // now that ITEMS has actual data, rebuild)
    IDX = ITEMS.map(function(i) {
      return {
        item: i,
        k: (i.b + ' ' + i.s + ' ' + i.n + ' ' + i.c).toLowerCase().replace(/&amp;/g, '&'),
        pop: POPULAR.indexOf(i.s.toUpperCase())
      };
    });
    IDX.sort(function(a, b) {
      var ap = a.pop, bp = b.pop;
      if (ap > -1 && bp > -1) return ap - bp;
      if (ap > -1) return -1;
      if (bp > -1) return 1;
      return (a.item.b + a.item.n).localeCompare(b.item.b + b.item.n);
    });

    console.log(`Loaded ${ITEMS.length} products (generated ${data.generated_at})`);
    return true;
  } catch (err) {
    console.error('Failed to load products.json:', err);
    showLoadError(err.message);
    return false;
  }
}

function showLoadError(msg) {
  const err = document.createElement('div');
  err.style.cssText =
    'position:fixed;top:0;left:0;right:0;background:#c62828;color:#fff;'
    + 'padding:12px 16px;font-family:sans-serif;z-index:9999;text-align:center;';
  err.innerHTML =
    'Unable to load product catalog. The calculator will not work. '
    + '<br><small>' + (msg || 'Unknown error') + '</small>';
  document.body.appendChild(err);
}

// Show a lightweight loading state while we fetch
(function showLoadingBanner() {
  const b = document.createElement('div');
  b.id = 'products-loading-banner';
  b.style.cssText =
    'position:fixed;top:0;left:0;right:0;background:#1b6cce;color:#fff;'
    + 'padding:8px 16px;font-family:sans-serif;z-index:9999;text-align:center;font-size:13px;';
  b.textContent = 'Loading product catalog…';
  document.body.appendChild(b);
})();
```

---

## Step 5 — Rewrite the INIT block

Find the final block (around line 1255–1260):

```js
// -- INIT --
pickItem('5000');
(function(){
  var siEl=document.getElementById('si'),ddEl=document.getElementById('dd');
  if(siEl&&ddEl)buildDDFor(siEl,ddEl);
})();
```

**Replace it with:**

```js
// -- INIT --
(async function init() {
  const ok = await loadProducts();
  const banner = document.getElementById('products-loading-banner');
  if (banner) banner.remove();
  if (!ok) return;

  // Pick a sensible default. Fall back gracefully if style 5000 is filtered out.
  const defaultStyle = ITEMS_BY_STYLE['5000'] ? '5000' :
                       ITEMS_BY_STYLE['PC54'] ? 'PC54' :
                       (ITEMS[0] && ITEMS[0].s);
  if (defaultStyle) pickItem(defaultStyle);

  const siEl = document.getElementById('si');
  const ddEl = document.getElementById('dd');
  if (siEl && ddEl) buildDDFor(siEl, ddEl);
})();
```

---

## Step 6 — Also move the `IDX` declaration to be a `let`

Around line 652 you'll find:

```js
var IDX=ITEMS.map(function(i){return{item:i,k:(i.b+' '+i.s+' '+i.n+' '+i.c).toLowerCase().replace(/&amp;/g,'&'),pop:POPULAR.indexOf(i.s.toUpperCase())};});
IDX.sort(function(a,b){var ap=a.pop,bp=b.pop;if(ap>-1&&bp>-1)return ap-bp;if(ap>-1)return -1;if(bp>-1)return 1;return(a.item.b+a.item.n).localeCompare(b.item.b+b.item.n);});
```

Change the first line from `var IDX=` to `let IDX=`. (This lets us reassign it inside `loadProducts()` once data arrives.) The initial value will be an empty array, which is fine — the fetch rebuilds it.

---

## That's it

After these 6 edits, save the file and refresh the calculator in your browser. You should see:

1. A brief blue "Loading product catalog…" banner at the top
2. Banner disappears once data is fetched
3. Search, product picker, and pricing work as before — but with live data

If you see a red error banner instead, open DevTools → Console and check the error message. Most likely causes:

- Wrong `PRODUCTS_JSON_URL` (typo or wrong repo name)
- Pages not deployed yet (run the workflow manually in GitHub Actions)
- Mixed content blocking (if your calculator is on HTTPS and Pages URL is HTTP — but GitHub Pages is always HTTPS, so this shouldn't happen)

---

## What's preserved, what's new

**Preserved:** All existing UI logic — color swatches, turnaround selection, screen-print color counts, size inputs, pricing math, the search dropdown. The calc function still reads `sel.p` and it still works.

**New access paths (for future UI work):**
- `ITEMS_BY_STYLE[styleNum]` gives you the full product object with all colors, size upcharges, sale data, and images
- `PRODUCTS_META.turnaround` has the timing/surcharge config from the feed
- `PRODUCTS_META.decoration_pricing` has the full SP/HT/EM matrices (useful if you want the calculator to use feed-driven pricing instead of the hardcoded constants already in the file)

---

## Phase 2 ideas (not needed for MVP)

Once the basics work, consider these enhancements that the rich schema enables:

1. **Color swatches** — render the `colors[]` array as clickable swatches under the product card; when a user clicks a color, swap the product image.
2. **Size-aware pricing** — the current UI assumes one price per item. For 2XL+ items, you could surface the upcharge from `ITEMS_BY_STYLE[style].size_upcharges` so the customer sees it.
3. **Sale badges** — if `case_sale_price` is active, show a "SALE" ribbon on the product card and show the strike-through regular price.
4. **Discontinued filter** — if `include_discontinued: true` is on, add a UI toggle to hide/show discontinued items in the search.
5. **Category filter tabs** — use the `category` field to group the search dropdown by category instead of brand.
