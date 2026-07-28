# Stripe checkout — setup

Two files: `stripeworker.js` (new Cloudflare Worker) and `cart.html` (updated).

**Nothing changes until you set `PAY_ENDPOINT` in `cart.html`.** With it blank, the cart keeps
the existing "Submit Order Request" behaviour exactly as it works today, so the updated
`cart.html` is safe to ship before any of this is done.

I never see or handle your Stripe keys — you enter them yourself in steps 3 and 6.

---

## 1. Get your Stripe keys

Stripe Dashboard → Developers → API keys. **Start with the test keys** (`sk_test_…`).
Do the whole setup in test mode, place a fake order, then swap in the live key.

## 2. Create the Worker

```bash
npm install -g wrangler
wrangler login
wrangler init alive-stripe --no-git
```

Replace the generated `src/index.js` with `stripeworker.js`.

## 3. Set the secrets

Run these yourself — the values never leave your machine:

```bash
wrangler secret put STRIPE_SECRET_KEY       # sk_test_… for now
wrangler secret put GHL_WEBHOOK_URL         # your existing LeadConnector hook URL
wrangler secret put STRIPE_WEBHOOK_SECRET   # whsec_… — you get this in step 6, set it after
```

## 4. Set the plain config

In `wrangler.toml`:

```toml
[vars]
ALLOWED_ORIGINS = "https://aliveprintshop.github.io,https://aliveprintshop.com"
CATALOG_URL = "https://aliveprintshop.github.io/PriceCalculator/products.json"
SUCCESS_URL = "https://aliveprintshop.github.io/PriceCalculator/cart.html"
CANCEL_URL  = "https://aliveprintshop.github.io/PriceCalculator/cart.html"
```

`ALLOWED_ORIGINS` must list every domain the cart is served from. Anything not on this list
is refused — this endpoint creates payments, so it deliberately does not allow `*`.

`SUCCESS_URL` is where the customer lands after paying. Point it at the page that shows the
cart. If your storefront embeds `cart.html` in an iframe, still point this at `cart.html`
itself — the customer will land on the standalone cart page showing the confirmation, which
works reliably. Pointing it at the wrapper page means the iframe can't read the `?paid=`
parameter and the confirmation won't show.

## 5. Deploy

```bash
wrangler deploy
```

Note the URL it prints, e.g. `https://alive-stripe.aliveprintshop.workers.dev`.
Check it responds:

```bash
curl https://alive-stripe.<you>.workers.dev/health     # {"ok":true}
```

## 6. Add the Stripe webhook

Stripe Dashboard → Developers → Webhooks → **Add endpoint**

- URL: `https://alive-stripe.<you>.workers.dev/webhook`
- Event: `checkout.session.completed`

Copy the signing secret (`whsec_…`) and set it:

```bash
wrangler secret put STRIPE_WEBHOOK_SECRET
wrangler deploy
```

**Don't skip this.** The webhook is how a payment gets confirmed. Customers close the tab
after paying more often than you'd think, and the browser redirect can't be relied on.

## 7. Turn it on in the cart

In `cart.html`, near the top of the script block:

```js
var PAY_ENDPOINT='https://alive-stripe.<you>.workers.dev';
```

The button becomes "Pay & Place Order", the heading becomes "Complete Your Order", and the
small print switches from "No payment now" to the Stripe line.

## 8. Test before going live

With `sk_test_…` still in place, place a real order through the cart using Stripe's test card:

- Card `4242 4242 4242 4242`, any future expiry, any CVC, any ZIP

Check all four:

1. You land back on the cart with **"Payment received — thank you!"** and the cart is empty
2. Stripe Dashboard (test mode) shows the payment
3. GHL received **two** records: one `awaiting_payment` when checkout started, one
   `paid` from the webhook
4. Hit Back / cancel on the Stripe page — your cart should still be intact

Then swap in the live key and redeploy:

```bash
wrangler secret put STRIPE_SECRET_KEY   # sk_live_…
wrangler deploy
```

---

## How it behaves

**The cart is not cleared until payment completes.** Abandoning the Stripe page, closing the
tab, or a card decline all leave the cart untouched.

**Orders reach you even if payment is abandoned.** The full order goes to GHL marked
`awaiting_payment` the moment checkout starts, sent via `sendBeacon` so it survives the
redirect. The webhook later sends a `paid` record. Both carry the same `orderRef`
(`AP-XXXX-XXXX`) so you can match them up — that's your abandoned-checkout follow-up list.

**If the Worker is unreachable**, the customer sees a message telling them their details were
saved and offering an email link, rather than a dead button.

## What the Worker checks

You chose to trust the cart's totals and reconcile manually, so it does **not** recompute the
quote. It does refuse the obvious forgeries:

- a unit price below that garment's own blank cost, read live from `products.json`
- a line total that doesn't match quantity × unit price (allowing size upcharges)
- a grand total above the sum of the lines, or less than half of it
- more than 50 items, negative quantities, invalid email

A promo discount still passes. A style not found in the catalog passes with no floor check —
a slow catalog fetch never blocks a real order.

**This is a floor, not a full price check.** Someone determined could still pay somewhat less
than quoted by editing values that stay above the blank cost. Your protection is reviewing
orders before printing. If you later want this closed properly, the pricing engine needs to
move into the Worker so it can recompute independently.

## Testing done

- Worker: 30/30 — including a slashed total, tampered line totals, an inflated total, a
  forged webhook signature, a replayed old event, body tampering, and a GHL outage
  (returns 500 so Stripe retries rather than dropping a paid order).
- Cart: 23/23 — pay mode, cancellation, completion, worker rejection, and the legacy
  no-Worker path still working unchanged.

**Not tested against real Stripe.** This sandbox has no network route to Stripe or Uploadcare,
so every test ran against a stub. Step 8 is the real verification.
