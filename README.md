# Zoya Deals: link-in-bio site (zoya.marqlo.in)

> **Backend:** deals, price history and click tracking live in Supabase. See [`supabase/README.md`](supabase/README.md). The site reads the public `deal_cards` view; "View deal" goes through the `go` function (click log + affiliate tag from the `config` table). `config.json` and `deals.json` are only the offline fallback.

This is a static site made of plain HTML, CSS and a little JS. It has no build step, no framework, no analytics and no third-party requests, and it runs as-is on GitHub Pages or Cloudflare Pages.

```
index.html              page shell, OG/Twitter meta tags, footer disclosure
assets/style.css        black void + cyan/violet glow, system "Avenir-like" font stack
assets/app.js           loads deals from Supabase (deal_cards), falls back to config.json + deals.json
assets/img/             avatar-256.webp, og.jpg (1200x630), favicons
favicon.ico             made from the channel watermark
deals.json              fallback deal list (used only if Supabase is unreachable)
config.json             affiliate IDs (empty means plain links)
images/deals/<slug>.webp  product cutouts
CNAME                   zoya.marqlo.in (used by GitHub Pages; Cloudflare ignores it)
.nojekyll               serve files as-is on GitHub Pages
_headers                cache and security headers (Cloudflare Pages only)
404.html, robots.txt
scripts/add_deal.py     reel job -> deal image + deals.json, --sql prints Supabase SQL
scripts/record_price.py record a price check (prints SQL)
supabase/               schema migrations, go edge function, backend docs (README.md)
qc/                     screenshots (git-ignored, not deployed)

Layout (minimal v2): one centred 440px column; each deal is a single list row
(thumbnail, name, price · store, chevron) linking to the store. The newest deal
gets a small "New" label. Search shows only when there are more than 6 deals.
mrp, hot, features and reel_url stay in deals.json but are not displayed.
```

## Deals: `deals.json`

```json
{ "deals": [ {
  "slug": "oneplus-nord-buds-3r",
  "title": "OnePlus Nord Buds 3R TWS Earbuds",
  "image": "images/deals/oneplus-nord-buds-3r.webp",
  "price": 1999,
  "mrp": 2499,                 // optional; shows strike-through and % off
  "store": "amazon",           // amazon | flipkart
  "url": "https://www.amazon.in/dp/B0FMDL81GS/?tag={AMAZON_TAG}",
  "date": "2026-10-23",        // newest date is pinned as "Latest from the reel"
  "reel_url": "https://…",     // optional "Watch the reel" button
  "hot": true,                 // kept in data, not shown
  "features": ["…"]            // kept in data, not shown
} ] }
```

## Affiliate tags: `config.json`

```json
{ "amazon_tag": "", "flipkart_affid": "" }
```

- If a value is empty, the `tag=` or `affid=` parameter is removed, so the visitor gets a plain product link (that is the current state).
- To set your IDs, fill in `amazon_tag` (e.g. `yourtag-21`) and/or `flipkart_affid` and redeploy. Every `{AMAZON_TAG}` or `{FLIPKART_AFFID}` placeholder is then filled in. A URL without a placeholder gets `?tag=` or `&affid=` appended.

## Adding a deal from a reel job

```bash
cd ~/projects/zoya-site
~/projects/ComfyUI/.venv/bin/python scripts/add_deal.py ~/projects/reel-jobs/<slug> \
    --asin B0XXXXXXXX --hot --reel-url https://youtube.com/shorts/XXXX
```

What the script does:
- It reads `<job>/product.json` (title, `price.value`, `price.mrp`, `asin` or `source_url`, `site`, `features`, `hero_cutout`).
- It trims the hero cutout, centres it on a 640px canvas and saves it as `images/deals/<slug>.webp`.
- It upserts the deal into `deals.json` by slug (newest first). Re-running it updates the deal in place and keeps the old date, hot flag and reel_url unless you override them.
- The slug defaults to the job folder name. You can override any field with `--slug --title --price --mrp --url --store --date --image`, and `--hot`/`--not-hot`.
- `--dry-run` prints the result without writing anything.
- The script only touches local files: no git, no deploy, no network. Commit and push yourself when you're happy with the result.
- Requires Python 3.9+ with Pillow (the ComfyUI venv has it).

## Preview locally

```bash
cd ~/projects/zoya-site && python3 -m http.server 8080   # open http://localhost:8080
```

Add `?q=buds` to the URL to pre-fill the search.

## Deploy, option A: GitHub Pages

1. Create a repo, e.g. `zoya-site` (public, or private on a paid plan). Then:
   `cd ~/projects/zoya-site && git init -b main && git add . && git commit -m "Zoya Deals site" && git remote add origin git@github.com:<user>/zoya-site.git && git push -u origin main`
2. In the repo, go to **Settings → Pages** and set **Source: Deploy from a branch**, then **Branch: main / (root)** and Save.
3. Under **Custom domain**, enter `zoya.marqlo.in` and Save. The `CNAME` file in the repo already says this.
4. At **Namecheap**, go to **Domain List → marqlo.in → Manage → Advanced DNS → Add New Record**:
   `CNAME Record | Host: zoya | Value: <user>.github.io. | TTL: Automatic`
   Use your GitHub username or org, not the repo name.
5. Wait for the DNS check to go green in Pages settings (minutes to about 1 hour), then tick **Enforce HTTPS**.
6. Optional: to stop anyone else claiming the domain, go to **GitHub → Settings (account) → Pages → Add a verified domain** for `marqlo.in`. It asks for a TXT record `_github-pages-challenge-<user>` at Namecheap.

## Deploy, option B: Cloudflare Pages (DNS stays at Namecheap)

You can connect the Git repo or upload directly.

**Connect Git:**
- Go to **Cloudflare dashboard → Workers & Pages → Create → Pages → Connect to Git**.
- Pick the repo. Leave Framework as **None**, the build command **empty**, and the output directory **`/`**.
- Click Deploy.

**Direct upload, no Git:**
```bash
cd ~/projects/zoya-site
rsync -a --delete --exclude qc --exclude _src --exclude scripts --exclude .git --exclude README.md ./ /tmp/zoya-dist/
npx wrangler login
npx wrangler pages project create zoya-deals --production-branch main
npx wrangler pages deploy /tmp/zoya-dist --project-name zoya-deals --branch main
```

The site is now at `https://zoya-deals.pages.dev` (if that name is taken, Cloudflare gives a different subdomain; use the one it shows you).

**Custom domain:**
1. Go to **Project → Custom domains → Set up a custom domain** and enter `zoya.marqlo.in`. Cloudflare will show the CNAME target to use.
2. At **Namecheap → Advanced DNS**, add `CNAME Record | Host: zoya | Value: zoya-deals.pages.dev | TTL: Automatic`.
3. Return to Cloudflare and wait for the domain to become **Active**. Cloudflare issues HTTPS automatically.

Use only one of the two hosts. The `zoya` CNAME can point at one target only.
