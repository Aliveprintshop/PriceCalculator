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
    title:     '50 Premium Next Level Tees',
    subtitle:  'NL6210 — our most popular tee',
    blurb:     '50 premium Next Level t-shirts with a full-color front & back design, one flat buy-it-now price.',

    // --- The locked deal ---
    qty:        50,        // total pieces — customer splits this across sizes, must total exactly this
    unitPrice:  13.00,     // $ shown as "each"
    total:      650.00,    // flat order total the customer pays
    compareAt:  750.00,    // struck-through "was" price to highlight the deal (omit to hide)

    // What's baked into the price (shown as the decoration line + benefit chips)
    decoration: 'Front & back full-color design included',
    turnaround: 'Standard — 10 business days',
    includes: [
      'Front & back full-color design',
      '1–8 color screen or full-color heat transfer',
      'No setup fee',
      'Free shipping',
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
  },

  {
    id:'g5000-50-frontback', style:'5000', active:true,
    badge:'Buy It Now',
    title:'50 Gildan Tees',
    subtitle:'5000 — classic heavyweight cotton tee',
    blurb:'A budget-friendly package of 50 Gildan 5000 tees with a front & back print, one flat price.',
    qty:50, unitPrice:9.00, total:450.00,
    decoration:'Screen Print — Front & Back print included',
    turnaround:'Standard — 10 business days',
    includes:['Front & back print included','Free shipping','No setup fee','Proof before we print'],
    forceColors:null, applySizeUpcharge:false
  },

  {
    id:'nike883681-24-embroidered', style:'883681', active:true,
    badge:'Buy It Now',
    title:'24 Nike Polos',
    subtitle:'883681 — Nike Dri-FIT polo',
    blurb:'A premium package of 24 Nike Dri-FIT polos with an embroidered left-chest logo, one flat price.',
    qty:24, unitPrice:52.08, total:1250.00,
    decoration:'Embroidery — Left chest logo included',
    turnaround:'Standard — 10 business days',
    includes:['Embroidered left chest','Free shipping','No setup fee','Proof before we print'],
    forceColors:null, applySizeUpcharge:false
  },

  {
    id:'cap112-50-embroidered', style:'112', active:true,
    badge:'Buy It Now',
    title:'50 Trucker Caps',
    subtitle:'112 — Richardson trucker cap',
    blurb:'A ready-to-go package of 50 Richardson 112 trucker caps with an embroidered front logo, one flat price.',
    qty:50, unitPrice:16.00, total:800.00,
    decoration:'Embroidery — Front logo included',
    turnaround:'Standard — 10 business days',
    includes:['Embroidered front','Free shipping','No setup fee','Proof before we print'],
    forceColors:null, applySizeUpcharge:false
  },

  {
    id:'st350-50-frontback', style:'ST350', active:true,
    badge:'Buy It Now',
    title:'50 Performance Tees',
    subtitle:'ST350 — Sport-Tek PosiCharge tee',
    blurb:'A team-ready package of 50 Sport-Tek ST350 performance tees with a front & back print, one flat price.',
    qty:50, unitPrice:14.00, total:700.00,
    decoration:'Screen Print — Front & Back print included',
    turnaround:'Standard — 10 business days',
    includes:['Front & back print included','Free shipping','No setup fee','Proof before we print'],
    forceColors:null, applySizeUpcharge:false
  }

];
