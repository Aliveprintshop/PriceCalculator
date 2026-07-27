# Alive Print Shop — Design Studio

A self-contained apparel design/mockup tool (`design-studio.html`) that lets customers
put art on a real product, place/scale/rotate it, remove backgrounds, and get an
automatic recommendation for the right decoration method — then save an approved
mockup + production spec straight into the cart.

## What it does

| Feature | Notes |
|---|---|
| **Product picker** | Browses the live `products.json` catalog, per-color swatches, front/back/sleeve views. |
| **Upload art** | PNG / JPG / SVG / WEBP / GIF, drag-and-drop or file picker. Multiple layers. |
| **Text tool** | Print-friendly fonts (Anton, Bebas Neue, Oswald, Bungee, Pacifico…), color, scale, rotate. |
| **Move / resize / rotate / flip / opacity / reorder** | Direct-manipulation handles + a layers list. |
| **AI background removal** | In-browser segmentation model (`@imgly/background-removal`, WASM). No server, no per-image cost, private. Manual color-dropper eraser as a backup. |
| **Automatic color counting** | Quantizes the art, counts spot colors, flags photographic shading. |
| **Print-method recommendation** | **1–8 solid colors → Screen Print**, more/gradients/photos → **Full Color DTF**, and **caps / jackets / bags → Embroidery**. Customer can override. Threshold is `CONFIG.SCREENPRINT_MAX_COLORS`. |
| **Print-area guides** | Toggleable front/back/left-chest/sleeve placement boxes (approximate). |
| **Print-quality (DPI) estimate** | Warns when uploaded art is too low-res for the chosen print size. |
| **AI Design Helper** | Chat for design advice + one-tap AI art generation that drops onto the garment (see Worker below). |
| **Save → cart** | Renders each decorated view, uploads the proof(s) to Uploadcare, stores a **design spec** (method, colors, placement, per-view layers) and hands off to the existing `aliveMockupAddToCart` cart flow. |

## Configure (top of `design-studio.html` → `CONFIG`)

```js
PRODUCTS_JSON_URL      // catalog feed (already set to the live Pages URL)
UPLOADCARE_PUB_KEY     // same account the mockup tool uses
UPLOADCARE_CDN         // custom CDN domain for this account
AI_ENDPOINT            // <-- paste your Cloudflare Worker URL to enable the AI helper
SCREENPRINT_MAX_COLORS // 8 by default (1..8 => screen print, more => DTF)
EMBROIDERY_CATEGORIES  // product categories decorated by embroidery
```

## AI Helper (optional) — `ai-design-worker.js`

The AI features call a tiny **Cloudflare Worker** that keeps your API keys off the
public site. It proxies:

- **chat** → Anthropic (Claude) for print/design advice
- **image** → OpenAI Images (`gpt-image-1`) for print-friendly art generation

Deploy steps are documented at the top of `ai-design-worker.js` (about 5 minutes,
free tier). After deploying, paste the Worker URL into `CONFIG.AI_ENDPOINT`.
Everything except AI works without it.

## Wiring it into the storefront (after approval)

The studio is **deployed but not linked** from the calculator yet. To make the
calculator's “Create a mockup” button open the studio instead of the old
background-remove tool, point `openMockup()` in `alive-pricing-calculator-v2.html`
at `design-studio.html` and pass `?style=<style>&color=<colorName>` (the studio
loads the full product, both views, and all colors from that). The existing
`aliveMockupAddToCart(url, spec)` contract already receives the proof URL, and now
an optional design-spec object as a second argument.

## Testing

`design-studio.html` is a single static file. Open it directly, or (interactive,
off the feature branch, no production deploy) via raw.githack. Automated
Playwright checks live under the session scratchpad and cover catalog load,
color-count → method routing, drag/resize, text, multi-view export, print guides,
and the AI wiring (against a mock endpoint).
