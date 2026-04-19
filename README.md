# SanMar Live Pricing Pipeline

Nightly sync from SanMar's SFTP → filtered `products.json` → hosted on GitHub Pages → consumed by `alive-pricing-calculator.html`.

This repo contains:

- `sync-sanmar.py` — the Python sync script
- `filters.json` — editable filter rules (categories, brands, discontinued handling, markup)
- `custom-products.xlsx` — template for non-SanMar items (merged into the output)
- `.github/workflows/sync.yml` — the nightly GitHub Action
- `requirements.txt` — pinned Python deps

Everything here runs for free on GitHub's infrastructure.

---

## One-time setup

### 1. Create a new GitHub repo

Name it something like `sanmar-pricing-data`. Public is fine — `products.json` doesn't contain anything sensitive (no FTP creds, no pricing lists for other customers). If you'd rather keep it private, you'll need GitHub Pro to use Pages with a private repo (or use a public repo just for the JSON output).

```bash
# From your local machine
git clone https://github.com/YOUR_USERNAME/sanmar-pricing-data.git
cd sanmar-pricing-data
```

Then copy all the files from this pipeline folder (`sync-sanmar.py`, `filters.json`, `custom-products.xlsx`, `requirements.txt`, and the `.github/` folder) into the repo root.

```bash
git add .
git commit -m "Initial pipeline setup"
git push
```

### 2. Add your SanMar FTP credentials as Secrets

In the repo on GitHub:

1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Add these two secrets:

| Name | Value |
|---|---|
| `SANMAR_FTP_USER` | Your SanMar customer number |
| `SANMAR_FTP_PASSWORD` | Your FTP password (NOT your sanmar.com password — they're separate. If you don't have one, call SanMar integration support at 1-800-426-6399 to get one set up.) |

These are encrypted and only visible to the Actions runner. You can't view them again after saving — only overwrite.

### 3. Enable GitHub Pages

1. Go to **Settings → Pages**
2. Under **Source**, select **GitHub Actions**
3. That's it — the workflow will deploy automatically.

After the first successful run, your `products.json` will be live at:

```
https://YOUR_USERNAME.github.io/sanmar-pricing-data/products.json
```

Save that URL — the calculator needs it.

### 4. Trigger the first run

Don't wait until midnight. Go to **Actions → Sync SanMar catalog nightly → Run workflow**, then click the green **Run workflow** button.

For the first test run, use the **limit** input to process only a small subset:

- Limit: `50` (or `100`) — processes just the first 50 styles for a faster smoke test.

This takes ~2–3 minutes. Leave it blank on subsequent runs to do the full catalog (~5–10 minutes, ~15,000 styles).

When the run finishes:
- `products.json` is committed to the repo
- The Pages site redeploys automatically
- You'll see the new URL in the **Actions → deploy** job output

Open that URL in a browser — you should see an index page showing the generated timestamp and product count. Click through to `products.json` to verify the actual data.

### 5. Wire the calculator

In `alive-pricing-calculator.html`, find the `const ITEMS = [...]` block (around line 640) and replace the hardcoded array with a fetch of the JSON. See the separate calculator-patch notes for the exact diff.

---

## Daily operations

### Editing filters

`filters.json` has inline comments (the `_*_comment` keys). Edit the file, commit, push. The next nightly sync applies your changes. Examples:

```json
// Only sell tees and hats
"category_whitelist": ["Tee Shirts", "Caps"],

// Exclude a few problematic styles
"style_blacklist": ["G800B", "DT6000Y"],

// Include discontinued items (shown with a flag in the calculator)
"include_discontinued": true,

// Drop a whole brand
"brand_blacklist": ["RABBIT SKINS"]
```

If you want to see what SanMar's category names actually look like, open the first run's `products.json` and scan the `category` fields — the whitelist/blacklist must match those exactly (case-insensitive).

### Adding custom (non-SanMar) products

1. Open `custom-products.xlsx` in Excel or Google Sheets
2. Follow the **Notes** tab for the schema
3. Each row = one product, with a unique `style` number
4. Save and commit the file

```bash
git add custom-products.xlsx
git commit -m "Add local supplier tote bags"
git push
```

Next nightly sync picks it up. If a custom `style` collides with a SanMar style, the custom row wins — useful for patching over bad SanMar data.

### Forcing a sync

Go to **Actions → Sync SanMar catalog nightly → Run workflow**. Useful after editing filters or custom products when you don't want to wait until 6am PST the next day.

---

## Troubleshooting

### "Authentication failed" in the sync log

- Double-check `SANMAR_FTP_USER` is your **customer number** (not your sanmar.com username)
- Double-check `SANMAR_FTP_PASSWORD` is the **FTP password** (not the sanmar.com password)
- If you've never used SanMar's FTP before, call integration support to activate the account

### "SDL file not found"

The script will print the SFTP root directory listing when this happens. Look for the actual file path — it's usually `SanMarPDD/SanMar_SDL_N.csv`, but some customer accounts differ. If yours is in a different location, edit the `SDL_FILENAMES` list at the top of `sync-sanmar.py`.

### Missing images for some products

SanMar sometimes has products without full image URLs (especially Coming Soon items or recently discontinued ones). These are dropped by default (`require_image: true` in filters.json). To keep them, set `require_image: false` — the calculator falls back to a gray placeholder.

### Sync runs but calculator shows no products

- Check the Pages URL in a browser — is `products.json` reachable?
- Check the browser DevTools Network tab when loading the calculator — is the fetch URL correct?
- Check CORS — GitHub Pages serves with permissive CORS, so this should Just Work, but verify the console doesn't show a CORS error
- If hosted on Hostinger, make sure the fetch is HTTPS (not HTTP — mixed content will be blocked)

### Running locally for development

```bash
# With real FTP credentials in your shell
export SANMAR_FTP_USER=123456
export SANMAR_FTP_PASSWORD=yourftppass
python sync-sanmar.py --limit 20

# Or with a local copy of the CSV, no FTP needed
python sync-sanmar.py --local ./SanMar_SDL_N.csv --limit 20

# Dry run (parses but doesn't write products.json)
python sync-sanmar.py --dry-run
```

---

## File structure reference

```
your-repo/
├── .github/
│   └── workflows/
│       └── sync.yml            # GitHub Action definition
├── sync-sanmar.py              # The sync script
├── filters.json                # Editable filter rules
├── custom-products.xlsx        # Your non-SanMar items
├── requirements.txt            # Python deps
├── products.json               # Generated output (committed by Action)
└── README.md                   # This file
```
