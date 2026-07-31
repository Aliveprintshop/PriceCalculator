/* =====================================================================
   ALIVE PRINT SHOP — BUY-IT-NOW DEALS (shared config)
   ---------------------------------------------------------------------
   This is the ONE place to manage the hidden "Deals" page.
   Both deals.html (the listing) and deal.html (the stripped-down
   calculator) read this file, so adding a deal = paste one block here.

   HOW TO ADD A DEAL
   -----------------
   Copy an existing { ... } block, give it a NEW unique `id`, point
   `style` at any catalog style number (it is cloned live from the
   nightly SanMar products.json feed — image, colors and sizes stay
   current automatically), then set the price fields. Set active:false
   to hide a deal without deleting it.

   Every deal is a flat "buy it now" price: `total` is what the customer
   pays for exactly `qty` pieces, regardless of the size mix they choose.
   ===================================================================== */

// Where a deal card opens (the stripped-down deal calculator). Relative by
// default, so it stays on GitHub Pages next to index.html. If you later host the
// deal calculator behind a WordPress page for brand consistency, set this to that
// URL, e.g. 'https://aliveprintshop.com/deal' — the code appends "?deal=<id>".
window.ALIVE_DEAL_CALC_URL = 'deal.html';

window.ALIVE_DEALS = [

  {
    id:        'nl6210-50-frontback',   // -> deals.html card links to deal.html?deal=nl6210-50-frontback
    style:     'NL6210',                // cloned from products.json (must exist in the feed)
    active:    true,

    // --- Card + header copy ---
    badge:     'Buy It Now',
    title:     '50 Next Level Tees',
    subtitle:  'NL6210 — our most popular tee',
    blurb:     'Skip the back-and-forth. A ready-to-go package of 50 premium Next Level tees with a front & back print, one flat price.',

    // --- The locked deal ---
    qty:        50,        // total pieces — customer splits this across sizes, must total exactly this
    unitPrice:  13.00,     // $ shown as "each"
    total:      650.00,    // flat order total the customer pays

    // What's baked into the price (shown as the imprint line + benefit chips)
    decoration: 'Screen Print — Front & Back print included',
    turnaround: 'Standard — 10 business days',
    includes: [
      'Front & back print included',
      'Free shipping',
      'No setup fee',
      'Proof before we print'
    ],

    // --- Options ---
    // Which colors to show as swatches. null = every color the catalog offers.
    // To limit the deal to specific colors, list exact catalog color names,
    // e.g. forceColors: ['Black','White','Heavy Metal'].
    forceColors: null,

    // Flat deals ignore 2XL+ size upcharges (the price is the price). Set true
    // only if you want the calculator to add the feed's size_upcharges on top.
    applySizeUpcharge: false
  }

  // ,{  id:'...', style:'...', ...next deal...  }

];
