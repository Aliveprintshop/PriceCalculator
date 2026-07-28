/**
 * Alive Print Shop — Stripe Checkout (Cloudflare Worker)
 * ======================================================
 * Keeps the Stripe SECRET key off the public website. cart.html calls this
 * Worker; the Worker talks to Stripe using secrets that only live on Cloudflare.
 *
 * Never put a Stripe secret key in cart.html. It is a public static file — anyone
 * could read the key and issue refunds against your account.
 *
 * ROUTES
 *   POST /create-session   -> { url }   Creates a Stripe Checkout Session for the cart
 *   POST /webhook          -> 200       Stripe calls this when payment completes
 *   GET  /health           -> { ok }
 *
 * ------------------------------------------------------------------
 * DEPLOY (about 10 minutes, free tier is plenty)
 * ------------------------------------------------------------------
 * 1. npm install -g wrangler && wrangler login
 *
 * 2. Create the Worker:
 *      wrangler init alive-stripe --no-git
 *      (replace the generated src/index.js with this file)
 *
 * 3. Set your secrets — YOU run these, the keys never pass through anyone else:
 *      wrangler secret put STRIPE_SECRET_KEY        # sk_live_... or sk_test_...
 *      wrangler secret put STRIPE_WEBHOOK_SECRET    # whsec_... (from step 6)
 *      wrangler secret put GHL_WEBHOOK_URL          # your existing LeadConnector hook
 *
 * 4. In wrangler.toml add your allowed origins:
 *      [vars]
 *      ALLOWED_ORIGINS = "https://aliveprintshop.github.io,https://aliveprintshop.com"
 *      CATALOG_URL = "https://aliveprintshop.github.io/PriceCalculator/products.json"
 *      SUCCESS_URL = "https://aliveprintshop.github.io/PriceCalculator/cart.html"
 *      CANCEL_URL  = "https://aliveprintshop.github.io/PriceCalculator/cart.html"
 *
 * 5. wrangler deploy      -> note the https://alive-stripe.<you>.workers.dev URL
 *    Put that URL in cart.html as PAY_ENDPOINT.
 *
 * 6. Stripe Dashboard -> Developers -> Webhooks -> Add endpoint
 *      URL:    https://alive-stripe.<you>.workers.dev/webhook
 *      Event:  checkout.session.completed
 *    Copy the signing secret (whsec_...) and set it in step 3.
 *
 * TEST FIRST with sk_test_ keys and card 4242 4242 4242 4242, any future expiry.
 */

const JSON_HEADERS = { 'Content-Type': 'application/json' };

/* ------------------------------------------------------------------ CORS */
function corsHeaders(request, env) {
  const origin = request.headers.get('Origin') || '';
  const allowed = (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
  // Only reflect an origin we explicitly trust — never "*", because this
  // endpoint creates payment sessions.
  const ok = allowed.indexOf(origin) > -1;
  return {
    'Access-Control-Allow-Origin': ok ? origin : (allowed[0] || ''),
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin'
  };
}

function json(body, status, extra) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: Object.assign({}, JSON_HEADERS, extra || {})
  });
}

/* ------------------------------------------------------- catalog + price floor */
let _catalog = null;
let _catalogAt = 0;

async function catalogFloor(env, style) {
  // Cached per isolate for an hour. A miss just means no floor check for that
  // style — we never block a real order because the catalog was slow.
  const now = Date.now();
  if (!_catalog || now - _catalogAt > 3600000) {
    try {
      const r = await fetch(env.CATALOG_URL, { cf: { cacheTtl: 3600 } });
      if (r.ok) {
        const data = await r.json();
        const list = Array.isArray(data) ? data : (data.products || []);
        const map = {};
        for (const p of list) {
          if (p && p.style) map[String(p.style).toUpperCase()] = Number(p.case_price) || 0;
        }
        _catalog = map;
        _catalogAt = now;
      }
    } catch (e) { /* fall through — no floor check */ }
  }
  if (!_catalog) return null;
  const v = _catalog[String(style || '').toUpperCase()];
  return (typeof v === 'number' && v > 0) ? v : null;
}

/**
 * The cart is client-side, so its numbers are attacker-controlled. We are not
 * recomputing the full quote here (deliberate decision — human review catches
 * pricing disputes), but we do refuse anything obviously forged:
 *   - a unit price below the blank garment's own case price
 *   - line totals that don't match qty x unit price
 *   - a grand total that doesn't match the sum of the lines
 * That stops "edit the total to $1" without duplicating the pricing engine.
 */
async function validateCart(env, items, claimedTotal) {
  const problems = [];
  if (!Array.isArray(items) || !items.length) return { ok: false, problems: ['Cart is empty.'] };
  if (items.length > 50) return { ok: false, problems: ['Too many items.'] };

  let sum = 0;
  for (let i = 0; i < items.length; i++) {
    const it = items[i] || {};
    const qty = Number(it.qty) || 0;
    const unit = Number(it.unitPrice) || 0;
    const line = Number(it.lineTotal) || 0;
    const label = (it.style || 'item ' + (i + 1));

    if (qty <= 0 || qty > 100000) problems.push(label + ': invalid quantity.');
    if (unit <= 0) problems.push(label + ': invalid unit price.');
    if (line <= 0) problems.push(label + ': invalid line total.');

    // qty x unit should equal the line, allowing for size upcharges and rounding.
    const upcharge = Number(it.sizeUpchargeTotal) || 0;
    const expected = qty * unit + upcharge;
    if (line > 0 && Math.abs(expected - line) > Math.max(1, expected * 0.02)) {
      problems.push(label + ': line total does not match quantity x unit price.');
    }

    const floor = await catalogFloor(env, it.style);
    if (floor && unit < floor) {
      problems.push(label + ': unit price is below our blank cost.');
    }
    sum += line;
  }

  const total = Number(claimedTotal) || 0;
  if (total <= 0) problems.push('Invalid order total.');
  // Promos legitimately reduce the total, so only flag a total ABOVE the lines
  // or absurdly below them.
  if (total > sum * 1.02 + 1) problems.push('Order total is higher than the sum of the items.');
  if (total < sum * 0.5) problems.push('Order total is far below the sum of the items.');

  return { ok: problems.length === 0, problems, lineSum: sum };
}

/* ------------------------------------------------------------------ Stripe */
function form(obj, prefix, out) {
  out = out || [];
  for (const k of Object.keys(obj)) {
    const v = obj[k];
    if (v === null || v === undefined || v === '') continue;
    const key = prefix ? prefix + '[' + k + ']' : k;
    if (typeof v === 'object' && !Array.isArray(v)) form(v, key, out);
    else if (Array.isArray(v)) v.forEach((el, i) => {
      if (typeof el === 'object') form(el, key + '[' + i + ']', out);
      else out.push([key + '[' + i + ']', String(el)]);
    });
    else out.push([key, String(v)]);
  }
  return out;
}

function itemLabel(it) {
  const bits = [it.brand, it.productName].filter(Boolean).join(' ');
  const color = it.color ? ' — ' + it.color : '';
  return (bits || 'Custom order').slice(0, 120) + color.slice(0, 40);
}

function itemDescription(it) {
  const bits = [];
  if (it.qty) bits.push(it.qty + ' pcs');
  if (it.decoLabel) bits.push(it.decoLabel);
  if (Array.isArray(it.locations) && it.locations.length) bits.push(it.locations.join(', '));
  if (it.turnaroundLabel) bits.push(it.turnaroundLabel);
  return bits.join(' · ').slice(0, 240) || undefined;
}

async function createSession(request, env) {
  let body;
  try { body = await request.json(); } catch (e) { return json({ error: 'Bad request.' }, 400); }

  const items = body.items || [];
  const customer = body.customer || {};
  const claimedTotal = body.total;

  if (!customer.email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(customer.email)) {
    return json({ error: 'A valid email address is required.' }, 400);
  }

  const check = await validateCart(env, items, claimedTotal);
  if (!check.ok) {
    return json({ error: 'We could not verify this order total. Please refresh the page and try again.', detail: check.problems }, 400);
  }

  // One Stripe line per cart item. quantity is 1 and the whole line total is the
  // unit_amount, because size upcharges and promos make per-piece cents rounding
  // disagree with the total the customer was shown.
  const lines = items.map(it => ({
    price_data: {
      currency: 'usd',
      unit_amount: Math.round(Number(it.lineTotal) * 100),
      product_data: { name: itemLabel(it), description: itemDescription(it) }
    },
    quantity: 1
  }));

  // A promo makes the claimed total lower than the sum of the lines; represent
  // the difference as a negative-free adjustment via Stripe's discount amount.
  const lineSum = check.lineSum;
  const discount = Math.max(0, Math.round((lineSum - Number(claimedTotal)) * 100));

  const payload = {
    mode: 'payment',
    success_url: (env.SUCCESS_URL || '') + '?paid={CHECKOUT_SESSION_ID}',
    cancel_url: (env.CANCEL_URL || '') + '?canceled=1',
    customer_email: customer.email,
    line_items: lines,
    payment_intent_data: {
      description: 'Alive Print Shop order — ' + (customer.name || customer.email).slice(0, 80)
    },
    // Kept small on purpose: Stripe caps metadata values at 500 characters.
    metadata: {
      customer_name: (customer.name || '').slice(0, 200),
      customer_phone: (customer.phone || '').slice(0, 60),
      company: (customer.company || '').slice(0, 200),
      item_count: String(items.length),
      piece_count: String(items.reduce((s, it) => s + (Number(it.qty) || 0), 0)),
      order_ref: body.orderRef || ''
    }
  };
  if (discount > 0) {
    payload.discounts = [{ coupon_data: { amount_off: discount, currency: 'usd', name: 'Promo', duration: 'once' } }];
  }

  const params = new URLSearchParams(form(payload));
  const r = await fetch('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + env.STRIPE_SECRET_KEY,
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: params.toString()
  });
  const data = await r.json();
  if (!r.ok) {
    return json({ error: 'Payment could not be started.', detail: (data.error && data.error.message) || '' }, 502);
  }
  return json({ url: data.url, id: data.id });
}

/* ---------------------------------------------------------------- webhook */
// Stripe signs the raw body: Stripe-Signature: t=<ts>,v1=<hmac sha256 of "t.body">
async function verifyStripeSignature(raw, header, secret, toleranceSec) {
  if (!header || !secret) return false;
  const parts = {};
  header.split(',').forEach(p => {
    const i = p.indexOf('=');
    if (i > 0) {
      const k = p.slice(0, i).trim();
      const v = p.slice(i + 1).trim();
      if (k === 'v1') (parts.v1 = parts.v1 || []).push(v);
      else parts[k] = v;
    }
  });
  if (!parts.t || !parts.v1 || !parts.v1.length) return false;

  // Reject replays of an old signature.
  const age = Math.abs(Math.floor(Date.now() / 1000) - Number(parts.t));
  if (!isFinite(age) || age > (toleranceSec || 300)) return false;

  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(parts.t + '.' + raw));
  const hex = [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, '0')).join('');

  // Constant-time compare against each provided v1.
  return parts.v1.some(v => {
    if (v.length !== hex.length) return false;
    let diff = 0;
    for (let i = 0; i < v.length; i++) diff |= v.charCodeAt(i) ^ hex.charCodeAt(i);
    return diff === 0;
  });
}

async function handleWebhook(request, env) {
  const raw = await request.text();
  const ok = await verifyStripeSignature(raw, request.headers.get('Stripe-Signature'), env.STRIPE_WEBHOOK_SECRET);
  // A failed signature means it isn't from Stripe. Never act on it.
  if (!ok) return new Response('Invalid signature', { status: 400 });

  let event;
  try { event = JSON.parse(raw); } catch (e) { return new Response('Bad JSON', { status: 400 }); }

  if (event.type === 'checkout.session.completed') {
    const s = event.data && event.data.object ? event.data.object : {};
    const md = s.metadata || {};
    const fd = new FormData();
    fd.append('event', 'payment_received');
    fd.append('paymentStatus', 'paid');
    fd.append('stripeSessionId', s.id || '');
    fd.append('stripePaymentIntent', s.payment_intent || '');
    fd.append('amountPaid', ((s.amount_total || 0) / 100).toFixed(2));
    fd.append('currency', (s.currency || 'usd').toUpperCase());
    fd.append('email', (s.customer_details && s.customer_details.email) || s.customer_email || '');
    fd.append('name', md.customer_name || '');
    fd.append('phone', md.customer_phone || '');
    fd.append('company', md.company || '');
    fd.append('itemCount', md.item_count || '');
    fd.append('pieceCount', md.piece_count || '');
    fd.append('orderRef', md.order_ref || '');
    try {
      if (env.GHL_WEBHOOK_URL) await fetch(env.GHL_WEBHOOK_URL, { method: 'POST', body: fd });
    } catch (e) {
      // Returning 200 anyway would make Stripe stop retrying. Return 500 so it
      // retries and the paid order is not lost.
      return new Response('Downstream failed', { status: 500 });
    }
  }
  return new Response('ok', { status: 200 });
}

/* ------------------------------------------------------------------ router */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const cors = corsHeaders(request, env);

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (url.pathname === '/health') return json({ ok: true }, 200, cors);

    // The webhook is called by Stripe, not a browser: no CORS, signature instead.
    if (url.pathname === '/webhook' && request.method === 'POST') return handleWebhook(request, env);

    if (url.pathname === '/create-session' && request.method === 'POST') {
      if (!env.STRIPE_SECRET_KEY) return json({ error: 'Payments are not configured yet.' }, 503, cors);
      try {
        const res = await createSession(request, env);
        const body = await res.json();
        return json(body, res.status, cors);
      } catch (e) {
        return json({ error: 'Unexpected error starting payment.' }, 500, cors);
      }
    }
    return json({ error: 'Not found' }, 404, cors);
  }
};

// Exported for local tests only.
export const __test = { validateCart, verifyStripeSignature, form, itemLabel, itemDescription };
