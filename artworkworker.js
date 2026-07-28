/* ============================================================================
   Alive Print Shop — artwork storage Worker (Cloudflare + R2)

   Replaces Uploadcare. Two jobs:

     POST /upload   customer artwork in, stored in R2, returns a URL
     GET  /f/<key>  serve it back

   Why files are served THROUGH the Worker rather than from a public bucket:
   it keeps the bucket private, and it means this code decides the response
   headers. That matters — an uploaded SVG is executable content, and serving
   one from a public bucket with the uploader's own content type is how a
   customer's "logo" becomes a script running on your domain. Everything here
   is served with a locked-down CSP, nosniff, and a content type derived from
   the extension we allow, never from what the uploader claimed.

   BINDINGS (wrangler.toml)
     r2_buckets      binding = "ART",  bucket_name = "alive-artwork"
   VARS
     ALLOWED_ORIGINS  comma-separated, e.g. "https://aliveprintshop.com,https://www.aliveprintshop.com"
     PUBLIC_BASE      this Worker's own public URL, e.g. "https://art.aliveprintshop.com"
   ========================================================================== */

const MAX_BYTES = 26214400;          // 25 MB — matches the calculator's own limit

// Extension -> the content type WE will serve it as. An extension not in this
// table is refused outright: an allowlist, never a blocklist.
const TYPES = {
  png:  'image/png',
  jpg:  'image/jpeg',
  jpeg: 'image/jpeg',
  gif:  'image/gif',
  webp: 'image/webp',
  svg:  'image/svg+xml',
  pdf:  'application/pdf',
  ai:   'application/postscript',
  eps:  'application/postscript',
  psd:  'image/vnd.adobe.photoshop',
  tif:  'image/tiff',
  tiff: 'image/tiff',
  zip:  'application/zip'
};
// Shown inline in the browser (the cart previews these). Everything else is
// sent as a download so it can never render in a page context.
const INLINE = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf']);

function originAllowed(request, env) {
  const origin = request.headers.get('Origin');
  if (!origin) return null;
  const list = String(env.ALLOWED_ORIGINS || '')
    .split(',').map(s => s.trim()).filter(Boolean);
  return list.includes(origin) ? origin : null;
}

// Never "*": this endpoint writes to storage, so only the shop's own pages
// may call it from a browser.
function cors(request, env) {
  const origin = originAllowed(request, env);
  const h = {
    'Vary': 'Origin',
    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
  };
  if (origin) h['Access-Control-Allow-Origin'] = origin;
  return h;
}

function json(body, status, request, env) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...cors(request, env) }
  });
}

function extOf(name) {
  const m = String(name || '').toLowerCase().match(/\.([a-z0-9]+)$/);
  return m ? m[1] : '';
}

// Strip anything that could climb out of the key namespace or confuse a
// Content-Disposition header.
//
// Runs of dots are collapsed. Not for traversal — an R2 key is a flat string,
// so "../" means nothing to the bucket — but the read path refuses any key
// containing "..", so a customer whose file happened to be named "..logo.png"
// would have it stored and then permanently unservable.
function safeName(name) {
  return String(name || 'artwork')
    .replace(/[\r\n"\\]/g, '')
    .replace(/[^A-Za-z0-9._ -]/g, '_')
    .replace(/\.{2,}/g, '.')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(-80) || 'artwork';
}

async function upload(request, env) {
  if (!originAllowed(request, env)) {
    return json({ error: 'origin not allowed' }, 403, request, env);
  }
  if (!env.ART) {
    return json({ error: 'storage not configured' }, 500, request, env);
  }

  // Cheap rejection before we buffer anything.
  const declared = Number(request.headers.get('Content-Length') || 0);
  if (declared && declared > MAX_BYTES + 8192) {
    return json({ error: 'file too large', max: MAX_BYTES }, 413, request, env);
  }

  let form;
  try {
    form = await request.formData();
  } catch (e) {
    return json({ error: 'could not read upload' }, 400, request, env);
  }

  const file = form.get('file');
  if (!file || typeof file === 'string' || !file.arrayBuffer) {
    return json({ error: 'no file' }, 400, request, env);
  }

  const name = safeName(file.name || form.get('name') || 'artwork');
  const ext = extOf(name);
  if (!TYPES[ext]) {
    return json({ error: 'file type not accepted', ext: ext || null }, 415, request, env);
  }

  const buf = await file.arrayBuffer();
  if (buf.byteLength === 0) {
    return json({ error: 'empty file' }, 400, request, env);
  }
  // The real check. Content-Length can lie; this cannot.
  if (buf.byteLength > MAX_BYTES) {
    return json({ error: 'file too large', max: MAX_BYTES }, 413, request, env);
  }

  const now = new Date();
  const key = now.getUTCFullYear() + '/' +
              String(now.getUTCMonth() + 1).padStart(2, '0') + '/' +
              crypto.randomUUID() + '/' + name;

  try {
    await env.ART.put(key, buf, {
      httpMetadata: { contentType: TYPES[ext] },
      customMetadata: {
        uploadedAt: now.toISOString(),
        origin: request.headers.get('Origin') || '',
        originalName: String(file.name || '').slice(0, 200)
      }
    });
  } catch (e) {
    return json({ error: 'could not store file' }, 502, request, env);
  }

  const base = String(env.PUBLIC_BASE || '').replace(/\/+$/, '') ||
               new URL(request.url).origin;
  return json({
    url: base + '/f/' + key.split('/').map(encodeURIComponent).join('/'),
    key,
    bytes: buf.byteLength,
    contentType: TYPES[ext]
  }, 200, request, env);
}

async function serve(request, env, url) {
  const key = decodeURIComponent(url.pathname.replace(/^\/f\//, ''));
  if (!key || key.includes('..')) return new Response('Not found', { status: 404 });
  if (!env.ART) return new Response('Storage not configured', { status: 500 });

  const obj = await env.ART.get(key);
  if (!obj) return new Response('Not found', { status: 404 });

  const ext = extOf(key);
  const type = TYPES[ext] || 'application/octet-stream';
  const inline = INLINE.has(ext) && url.searchParams.get('dl') !== '1';
  const filename = safeName(key.split('/').pop());

  return new Response(obj.body, {
    headers: {
      'Content-Type': type,
      'Content-Length': String(obj.size),
      // Keys are immutable (a UUID per upload), so this can cache hard.
      'Cache-Control': 'public, max-age=31536000, immutable',
      'Content-Disposition': (inline ? 'inline' : 'attachment') +
                             '; filename="' + filename + '"',
      // Neutralises an uploaded SVG or HTML-ish file: no scripts, no network,
      // no sniffing us into treating it as something else.
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; sandbox",
      'X-Content-Type-Options': 'nosniff',
      'Access-Control-Allow-Origin': '*'   // read-only, safe to share
    }
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors(request, env) });
    }
    if (request.method === 'POST' && url.pathname === '/upload') {
      return upload(request, env);
    }
    if (request.method === 'GET' && url.pathname.startsWith('/f/')) {
      return serve(request, env, url);
    }
    if (request.method === 'GET' && url.pathname === '/health') {
      return json({ ok: true, storage: !!env.ART }, 200, request, env);
    }
    return json({ error: 'not found' }, 404, request, env);
  }
};
