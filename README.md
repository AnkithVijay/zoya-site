# Zoya Deals: link-in-bio site (zoya.marqlo.in)

> **Backend:** products, price history and click tracking live in Supabase; `products.product_id` is the key everything links to. See [`supabase/README.md`](supabase/README.md). The page reads the public `product_cards` view live (it paints the last good response from `localStorage` first, or placeholder rows on a first visit), and product images live in the public Storage bucket `product-images`. **Adding, editing, hiding or repricing a product is a database change only: no commit, no deploy.** "View deal" goes through the `go` function (`?p=<product_id>`: click log + affiliate tag from the `config` table).

This is a static site made of plain HTML, CSS and a little JS. It has no build step, no framework and no analytics. The only third-party requests are the Supabase read and the `/go` redirect. It runs as-is on GitHub Pages or Cloudflare Pages.

```
index.html              page shell, OG/Twitter meta tags, footer disclosure
assets/style.css        minimal dark list, system font stack
assets/app.js           reads product_cards from Supabase (localStorage cache, skeleton on first visit)
assets/img/             avatar-256.webp, og.jpg (1200x630), favicons
favicon.ico             made from the channel watermark
config.json             affiliate IDs, used only for direct links when Supabase is down
CNAME                   zoya.marqlo.in (used by GitHub Pages; Cloudflare ignores it)
.nojekyll               serve files as-is on GitHub Pages
_headers                cache and security headers (Cloudflare Pages only)
404.html, robots.txt
scripts/add_product.py  reel job -> image uploaded to Storage + Supabase upsert (--sql prints SQL, --push writes)
scripts/add_deal.py     deprecated alias for add_product.py (old flags still work)
scripts/export_products.py  OPTIONAL local backup of product_cards (git-ignored products.json; the site doesn't read it)
scripts/record_price.py record a price check (prints SQL)
supabase/               schema migrations, go edge function, backend docs (README.md)
qc/                     screenshots (git-ignored, not deployed)

Layout: one centred 440px column; each product is a single list row (thumbnail, name,
price line, one muted highlights line, store · price date, chevron). The newest product
gets a small "New" label. Search shows only when there are more than 6 products.
Order: featured first, then sort_order, then newest.
```

## Products: Supabase `product_cards`

The site renders the public `product_cards` view (fields: `product_id`, `title`, `brand`,
`category`, `tagline`, `highlights`, `image_url`, `store`, `store_product_id`, `product_url`,
`reel_url`, `instagram_url`, `listing_price`, `current_price`, `previous_price`,
`price_checked_at`, `featured`, `sort_order`, `created_at`, ...). `image_url` is the public
Storage URL `https://rrsxsqtfotxkjgkbqnpx.supabase.co/storage/v1/object/public/product-images/<product_id>.webp`.

- `listing_price` (MRP) shows a strike-through and % off when it's above `current_price`.
- `previous_price` shows a small ↓/↑ change marker.
- `highlights` (max 4) render as one muted line; `tagline` is used when there are none.
- `reel_url` / `instagram_url` are stored but not rendered.

## Affiliate tags

The tag lives in Supabase `config` (the `go` function adds it). `config.json`
(`{ "amazon_tag": "", "flipkart_affid": "" }`) is only used for direct store links when
Supabase can't be reached; an empty value means a plain link.

## Adding a product from a reel job (no deploy)

```bash
cd ~/projects/zoya-site
~/projects/ComfyUI/.venv/bin/python scripts/add_product.py ~/projects/reel-jobs/<job> \
    --product-id brand-model --asin B0XXXXXXXX --featured \
    --reel-url https://youtube.com/shorts/XXXX --instagram-url https://www.instagram.com/reel/XXXX/ --sql
# then run the printed SQL with the Supabase connector (execute_sql). That's it: it's live.
```

What `add_product.py` does:
- It reads `<job>/product.json` (title, brand, `price.value`, `price.mrp`, `asin` or `source_url`, `site`, `features`, `category`/`category_guess`, `hero_cutout`).
- It trims the hero cutout, centres it on a 640px webp and uploads it to Storage as `product-images/<product_id>.webp` (overwrites; `image_url` gets `?v=<upload time>` so a replaced image shows at once).
- With `--sql` it prints the idempotent upsert + price check for `execute_sql`; with `--push` it writes over REST.
- The upload and `--push` need the **service-role key**: `export SUPABASE_SERVICE_ROLE_KEY=...` or save it in `~/.config/zoya-deals/service_role_key` (`chmod 600`). **Never commit it** or put it in `config.json` / the site JS. `--no-upload` skips the upload (the webp is saved next to `product.json`, `image_url` is left as is).
- `--product-id` defaults to the slugified title. Pass a short `brand-model` id; it's the permanent key.
- Overrides: `--title --brand --category --tagline --highlight (x4) --price --mrp --url --store --image --sort-order --reel-url --instagram-url`, `--featured`/`--not-featured`. `--dry-run` uploads and writes nothing.
- No git, no deploy.
- Requires Python 3.9+ with Pillow (the ComfyUI venv has it).

Price change: `python3 scripts/record_price.py <product_id> <price> [--mrp N]` (prints SQL). Hide: `update public.products set active = false where product_id = '<id>';`. Both are live at once.

**What still needs a deploy (commit + push):** changes to the page itself: `index.html`, `assets/*` (layout, styles, JS), `config.json` (fallback tag for direct links), the avatar/OG images, `404.html`, `_headers`, `CNAME`.

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
rsync -a --delete --exclude qc --exclude _src --exclude scripts --exclude supabase --exclude .git --exclude README.md --exclude products.json ./ /tmp/zoya-dist/
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
