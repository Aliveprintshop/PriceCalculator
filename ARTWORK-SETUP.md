# Artwork storage — setup (Cloudflare Worker + R2)

Replaces Uploadcare. Two files: `artworkworker.js` (new) and
`alive-pricing-calculator-v2.html` (updated).

**Nothing changes until you set `ART_ENDPOINT`.** Left blank, the calculator
uses the old Uploadcare path exactly as before, so this is safe to publish
before the Worker exists.

---

## Why

On 28 July 2026 Uploadcare began refusing every upload from the calculator with
`403 UploadFailedError`. Established by testing, not guesswork:

- the public key is **valid** — a deliberately wrong key returns a different
  error (`ProjectPublicKeyInvalidError`)
- the read API still answers for that key
- **every** upload path fails identically — with a file, via `from_url`, and
  with **no file attached at all**. A fileless request should fail validation
  long before a 403, so the block sits ahead of any request handling
- it fails the same from `wikipedia.org` as from `aliveprintshop.com`, so it is
  not a domain allowlist
- a file the calculator had previously uploaded successfully now returns **404**

That is an account-level block. Worth checking the Uploadcare billing page
regardless — **artwork from earlier orders may no longer be retrievable.**

---

## Steps

### 1. Create the R2 bucket

Cloudflare dashboard → **R2** → *Create bucket* → name it `alive-artwork`.
Leave it **private**. Files are served through the Worker, which is what lets
the Worker control the response headers (see *Security* below).

### 2. Create the Worker

Workers & Pages → *Create* → *Worker* → name it `alive-artwork`.
Paste the contents of `artworkworker.js` and deploy.

### 3. Bind the bucket

Worker → **Settings → Bindings → Add → R2 bucket**

| Field | Value |
|---|---|
| Variable name | `ART` |
| R2 bucket | `alive-artwork` |

The variable name must be exactly `ART`.

### 4. Add the two variables

Settings → **Variables and Secrets** (plain text, not secrets):

| Name | Value |
|---|---|
| `ALLOWED_ORIGINS` | `https://aliveprintshop.com,https://www.aliveprintshop.com` |
| `PUBLIC_BASE` | the Worker's own URL, e.g. `https://alive-artwork.aliveprintshop.workers.dev` |

`ALLOWED_ORIGINS` is the list of sites allowed to upload. It is never `*` —
this endpoint writes to storage. If you later serve the calculator from another
domain, add it here or uploads from it will be refused.

`PUBLIC_BASE` is what goes into the artwork URLs stored on every order, so
**it must be a URL that will not change.** Prefer a custom domain (step 6).

### 5. Check it is alive

Open `https://<your-worker-url>/health` — expect:

```json
{"ok":true,"storage":true}
```

`"storage":false` means the R2 binding is missing or misnamed.

### 6. Optional but recommended — a custom domain

Worker → Settings → **Domains & Routes** → *Add custom domain* →
e.g. `art.aliveprintshop.com`. Then set `PUBLIC_BASE` to that.

Artwork URLs are written into orders permanently. A `workers.dev` URL ties
those links to a subdomain you do not really own; a custom domain means you can
move the Worker later without breaking every historic order.

### 7. Point the calculator at it

In `alive-pricing-calculator-v2.html`, find:

```js
var ART_ENDPOINT='';
```

and set it:

```js
var ART_ENDPOINT='https://art.aliveprintshop.com';
```

No trailing slash needed — one is stripped either way.

### 8. Test with a real upload

Load the calculator, pick a product, upload a logo. The row should read
**uploaded**, not *upload failed*. Then open the artwork link from the cart and
confirm the image loads.

---

## What the Worker does

| Route | Purpose |
|---|---|
| `POST /upload` | multipart form with a `file` field → stores it → returns `{url, key, bytes, contentType}` |
| `GET /f/<key>` | serves the file back. `?dl=1` forces a download |
| `GET /health` | liveness plus whether the bucket is bound |

Keys are `YYYY/MM/<uuid>/<filename>`, so two customers uploading `logo.png` can
never collide, and you can find a month's artwork by prefix in the R2 browser.

## Limits

- **25 MB** per file, matching the calculator's own limit. Checked against the
  real byte count, not the `Content-Length` header, which a client can understate.
- Accepted: `png jpg jpeg gif webp svg pdf ai eps psd tif tiff zip`.
  An allowlist — anything else is refused with a 415.

## Security

Files are served **through the Worker**, not from a public bucket, so this code
decides the response headers. That matters more than it sounds: an uploaded SVG
is executable content, and serving one from a public bucket under the
uploader's own content type is how a customer's "logo" becomes a script running
on your domain. Every response therefore carries:

- a content type derived from the extension **we** allow, never from what the
  uploader claimed
- `Content-Disposition: attachment` for anything not a plain raster or PDF, so
  an SVG downloads rather than renders
- `Content-Security-Policy: default-src 'none'; sandbox` and
  `X-Content-Type-Options: nosniff`

`/upload` accepts requests only from `ALLOWED_ORIGINS`.

**One thing this does not do:** an `Origin` header only stops *browsers* on
other sites. It does not stop someone posting directly with curl, and there is
no rate limit in the code. Add one in the dashboard —
**Security → WAF → Rate limiting rules**, something like 20 requests per minute
per IP on `/upload`. Without it the endpoint is, in principle, free file
hosting for anyone who finds it.

## Cost

R2's free tier is 10 GB stored and 1 million writes a month, and R2 has no
egress charges. Customer artwork will not come close. Verify current pricing
before relying on the numbers — they change.

## Migrating old artwork

Not attempted, because Uploadcare is currently returning 404 for stored files.
If billing is restored and old files come back, they can be copied across; until
then, orders whose only copy lived on Uploadcare will need the artwork
requested from the customer again.

## Testing done

- **52 Worker tests** against a mock R2: happy path, origin refusal, oversize
  (including an understated `Content-Length`), disallowed and missing
  extensions, empty file, missing bucket binding, path traversal in filenames,
  non-latin names, very long names, SVG handling, cache and CSP headers, key
  collisions, routing and preflight.
- **20 end-to-end tests** driving the real calculator in a browser against this
  exact Worker code: upload, byte-identical download, background-removal
  re-upload keeping the original, cart payload, and each rejection surfacing to
  the customer.

Not tested against real Cloudflare — the sandbox has no route to it, so the R2
binding was mocked. Step 5 and step 8 are what confirm the real thing.
