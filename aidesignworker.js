/**
 * Alive Print Shop — AI Design Helper (Cloudflare Worker)
 * =======================================================
 * A tiny serverless proxy that keeps your API keys OFF the public website.
 * The Design Studio (design-studio.html) calls this Worker; the Worker calls
 * the AI providers using secrets that only live on Cloudflare.
 *
 * It exposes ONE endpoint (POST /) with two actions:
 *   { action: "chat",  messages: [...], context: {...} }   -> { text }
 *   { action: "image", prompt: "...",   context: {...} }   -> { images: ["data:image/png;base64,..."] }
 *
 *  - "chat"  is powered by Anthropic (Claude) — great print/design advice.
 *  - "image" is powered by OpenAI Images (gpt-image-1) — Anthropic has no image
 *            model, so image generation uses OpenAI. You can swap this for
 *            Stability/Ideogram/etc. in generateImage() below.
 *
 * ------------------------------------------------------------------
 * DEPLOY (about 5 minutes, free tier is plenty):
 * ------------------------------------------------------------------
 * 1. Install Wrangler (Cloudflare's CLI) and log in:
 *       npm install -g wrangler
 *       wrangler login
 *
 * 2. Create the Worker project:
 *       wrangler init alive-ai --yes
 *    Replace the generated src/index.js with THIS file's contents.
 *
 * 3. Add your secrets (they are encrypted, never in the code / never public):
 *       wrangler secret put ANTHROPIC_API_KEY      # for the chat helper
 *       wrangler secret put OPENAI_API_KEY         # for image generation
 *
 * 4. Lock it to your site so nobody else can burn your credits.
 *    In wrangler.toml add:
 *       [vars]
 *       ALLOWED_ORIGINS = "https://aliveprintshop.com,https://aliveprintshop.github.io"
 *
 * 5. Deploy:
 *       wrangler deploy
 *    Copy the printed URL (e.g. https://alive-ai.<you>.workers.dev) and paste it
 *    into design-studio.html -> CONFIG.AI_ENDPOINT.
 * ------------------------------------------------------------------
 */

const CHAT_MODEL  = "claude-sonnet-4-5-20250929"; // fast + capable; adjust as you like
const IMAGE_MODEL = "gpt-image-1";

export default {
  async fetch(request, env) {
    const cors = corsHeaders(request, env);

    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    if (request.method !== "POST")
      return json({ error: "POST only" }, 405, cors);

    let body;
    try { body = await request.json(); }
    catch { return json({ error: "Invalid JSON" }, 400, cors); }

    try {
      if (body.action === "image") {
        const images = await generateImage(body.prompt || "", body.context || {}, env);
        return json({ images }, 200, cors);
      }
      // default: chat
      const text = await chat(body.messages || [], body.context || {}, env);
      return json({ text }, 200, cors);
    } catch (err) {
      return json({ error: String(err && err.message || err) }, 500, cors);
    }
  }
};

/* ---------------- Chat: Anthropic (Claude) ---------------- */
async function chat(messages, context, env) {
  if (!env.ANTHROPIC_API_KEY) throw new Error("ANTHROPIC_API_KEY not set");

  const system =
    "You are the design assistant for Alive Print Shop, an apparel decoration company " +
    "(screen printing, embroidery, DTF/heat transfers, and custom patches). " +
    "Help the customer shape a print-ready design concept. Be concise, friendly and practical. " +
    "Give specific guidance on text, layout, and color choices. Remember our production rules: " +
    "1–8 solid spot colors print great as SCREEN PRINT; more colors, gradients or photos should be " +
    "FULL-COLOR DTF transfers; caps, jackets and bags are usually EMBROIDERY (avoid tiny text / fine detail there). " +
    "When the customer is ready for art, tell them to tap the Generate button. " +
    (context.product ? `They are working on: ${context.product} ${context.color || ""}. ` : "") +
    "Keep replies under 120 words.";

  // Anthropic expects [{role:'user'|'assistant', content:'...'}]
  const msgs = messages
    .filter(m => m && (m.role === "user" || m.role === "assistant") && m.content)
    .map(m => ({ role: m.role, content: String(m.content) }));

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01"
    },
    body: JSON.stringify({ model: CHAT_MODEL, max_tokens: 400, system, messages: msgs })
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error?.message || "Anthropic error");
  return (data.content || []).map(c => c.text || "").join("").trim() || "…";
}

/* ---------------- Image: OpenAI Images (gpt-image-1) ---------------- */
async function generateImage(prompt, context, env) {
  if (!env.OPENAI_API_KEY) throw new Error("OPENAI_API_KEY not set");

  // Steer the model toward PRINT-FRIENDLY art: bold, isolated subject, clean edges,
  // limited palette, transparent-friendly. This keeps color counts low so more jobs
  // qualify for screen printing, and cuts out messy photographic backgrounds.
  const engineered =
    `${prompt}. Design for apparel screen printing / DTF transfer: bold, high-contrast, ` +
    `clean vector-style illustration, limited flat color palette, crisp edges, centered subject, ` +
    `NO background scene, NO photographic realism, isolated on a plain white background, ` +
    `no mockup, no t-shirt, just the graphic itself.`;

  const res = await fetch("https://api.openai.com/v1/images/generations", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "authorization": `Bearer ${env.OPENAI_API_KEY}`
    },
    body: JSON.stringify({
      model: IMAGE_MODEL,
      prompt: engineered,
      n: 2,
      size: "1024x1024",
      background: "transparent"
    })
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error?.message || "OpenAI image error");
  // gpt-image-1 returns b64_json by default
  return (data.data || []).map(d =>
    d.b64_json ? `data:image/png;base64,${d.b64_json}` : d.url
  ).filter(Boolean);
}

/* ---------------- helpers ---------------- */
function corsHeaders(request, env) {
  const origin = request.headers.get("Origin") || "";
  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
  // If ALLOWED_ORIGINS is unset, allow all (fine for testing; set it before production).
  const ok = allowed.length === 0 || allowed.some(a => origin === a || origin.endsWith(a.replace(/^https?:\/\//, "")));
  return {
    "Access-Control-Allow-Origin": ok && origin ? origin : (allowed[0] || "*"),
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin"
  };
}
function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { "content-type": "application/json", ...(cors || {}) }
  });
}
