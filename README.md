# Zoya Deals: link-in-bio site (zoya.marqlo.in)

> **Backend:** products, price history and click tracking live in Supabase; `products.product_id` is the key everything links to. See [`supabase/README.md`](supabase/README.md). The page paints instantly from `products.json` (a snapshot of the public `product_cards` view) and then refreshes from Supabase in the background. "View deal" goes through the `go` function (`?p=<product_id>`: click log + affiliate tag from the `config` table).

This is a static site made of plain HTML, CSS and a little JS. It has no build step, no framework and no analytics. The only third-party requests are the Supabase read and the `/go` redirect. It runs as-is on GitHub Pages or Cloudflare Pages.

```
index.html              page shell, OG/Twitter meta tags, footer disclosure
assets/style.css        minimal dark list, system font stack
assets/app.js           paints products.json, then refreshes from Supabase (product_cards)
assets/img/             avatar-256.webp, og.jpg (1200x630), favicons
favicon.ico             made from the channel watermark
products.json           snapshot of product_cards (regenerate: scripts/export_products.py)
config.json             affiliate IDs, used only for direct links when Supabase is down
images/products/<product_id>.webp  product cutouts
CNAME                   zoya.marqlo.in (used by GitHub Pages; Cloudflare ignores it)
.nojekyll               serve files as-is on GitHub Pages
_headers                cache and security headers (Cloudflare Pages only)
404.html, robots.txt
scripts/add_product.py  reel job -> product image + products.json entry, --sql prints Supabase SQL
scripts/add_deal.py     deprecated alias for add_product.py (old flags still work)
scripts/export_products.py  Supabase product_cards -> products.json (no secret needed)
scripts/record_price.py record a price check (prints SQL)
supabase/               schema migrations, go edge function, backend docs (README.md)
qc/                     screenshots (git-ignored, not deployed)

Layout: one centred 440px column; each product is a single list row (thumbnail, name,
price line, one muted highlights line, store · price date, chevron). The newest product
gets a small "New" label. Search shows only when there are more than 6 products.
Order: featured first, then sort_order, then newest.
```

## Products: `products.json`

Generated, don't hand-edit. Same fields as the `product_cards` view (minus click counts):

```json
{ "updated": "2026-10-23T09:58:55+00:00", "source": "supabase", "products": [ {
  "product_id": "oneplus-nord-buds-3r",
  "title": "OnePlus Nord Buds 3R TWS Earbuds", "brand": "OnePlus", "category": "tws_earbuds",
  "tagline": null, "highlights": ["12.4mm titanium drivers", "47ms low latency", "54 hours battery", "dual connection"],
  "image_url": "images/products/oneplus-nord-buds-3r.webp",
  "store": "amazon", "store_product_id": "B0FMDL81GS", "product_url": "https://www.amazon.in/dp/B0FMDL81GS",
  "reel_url": null, "listing_price": null, "current_price": 1999, "previous_price": null,
  "price_checked_at": "2026-10-23T09:44:41.104295+00:00", "featured": true, "sort_order": 0,
  "created_at": "2026-10-23T09:44:41.104295+00:00"
} ] }
```

- `listing_price` (MRP) shows a strike-through and % off when it's above `current_price`.
- `previous_price` shows a small ↓/↑ change marker.
- `highlights` (max 4) render as one muted line; `tagline` is used when there are none.

## Affiliate tags

The tag lives in Supabase `config` (the `go` function adds it). `config.json`
(`{ "amazon_tag": "", "flipkart_affid": "" }`) is only used for direct store links when
Supabase can't be reached; an empty value means a plain link.

## Adding a product from a reel job

```bash
cd ~/projects/zoya-site
~/projects/ComfyUI/.venv/bin/python scripts/add_product.py ~/projects/reel-jobs/<job> \
    --product-id oneplus-nord-buds-3r --asin B0XXXXXXXX --featured --reel-url https://youtube.com/shorts/XXXX --sql
# run the printed SQL with the Supabase connector (execute_sql), then:
python3 scripts/export_products.py      # resync products.json from Supabase
git add -A && git commit -m "Add <product_id>" && git push
```

What `add_product.py` does:
- It reads `<job>/product.json` (title, brand, `price.value`, `price.mrp`, `asin` or `source_url`, `site`, `features`, `category`/`category_guess`, `hero_cutout`).
- It trims the hero cutout, centres it on a 640px canvas and saves it as `images/products/<product_id>.webp`.
- It upserts the product into `products.json` by `product_id` and, with `--sql`, prints the Supabase upsert + price check.
- `--product-id` defaults to the slugified title. Pass a short `brand-model` id; it's the permanent key.
- Overrides: `--title --brand --category --tagline --highlight (x4) --price --mrp --url --store --image --sort-order`, `--featured`/`--not-featured`. `--dry-run` writes nothing.
- No git, no deploy. Network only with `--push` (needs `SUPABASE_SERVICE_ROLE_KEY` in env; never commit it).
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
