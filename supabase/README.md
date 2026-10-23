# Zoya Deals: Supabase backend

Project ref: `rrsxsqtfotxkjgkbqnpx` (org "zoya"). API URL: `https://rrsxsqtfotxkjgkbqnpx.supabase.co`

## What's in the database

`products.product_id` is the primary key; `price_history` and `clicks` reference it
(`on delete cascade, on update cascade`).

| Object | What it holds | Browser (anon) access |
|---|---|---|
| `products` | one row per product: `product_id` (slug pk), `title`, `brand`, `category`, `tagline`, `highlights` (text[], max 4), `image_url`, `store`, `store_product_id` (ASIN / Flipkart PID), `product_url` (clean, no tag), `reel_url`, `listing_price` (MRP, null if unconfirmed), `current_price`, `price_checked_at`, `click_count`, `featured`, `sort_order`, `active`, `created_at`, `updated_at` | read (active rows only) |
| `price_history` | every price check: `product_id`, `price`, `listing_price`, `source` (`manual` / `paapi` / `keepa`), `checked_at` | read |
| `clicks` | one row per "View deal" tap: `product_id`, `clicked_at`, `referrer`, `country`, `ua_hash` (SHA-256 of the user agent; no IP stored) | none |
| `config` | single row: `amazon_tag`, `flipkart_affid` (read by the `go` function) | none |
| `product_cards` (view, `security_invoker`) | what the site renders: active products + `previous_price` (second-newest check) | read |

Triggers:
- inserting into `price_history` updates the product's `current_price`, `listing_price` (if given) and `price_checked_at` (only if the check is the newest one);
- inserting or deleting `clicks` keeps `products.click_count` in sync, so the public view never has to read `clicks`.

RLS is on for every table. anon/authenticated have only `SELECT` on `products`, `price_history` and `product_cards`.
Every write goes through the service role (the `go` edge function, the Supabase connector, or a script with the service key in env).

Schema source, in order: `migrations/20261023_init_deals.sql` (v1, deals), `migrations/20261023_harden_rls_auto_enable.sql`, `migrations/20261023_products.sql` (current; rebuilds around `products`). All applied.

## Click tracker: `go` edge function

`GET https://rrsxsqtfotxkjgkbqnpx.supabase.co/functions/v1/go?p=<product_id>`, deployed with `verify_jwt = false`. Source: `functions/go/index.ts`.
`?d=<id>` (the old parameter) still works, and the old id `nord-buds-3r` maps to `oneplus-nord-buds-3r`.

1. It looks up the product with the service role. An unknown or inactive product returns **404** (lookup error: 503).
2. It logs a `clicks` row (referrer, country if a geo header is present, `ua_hash`). HEAD requests and obvious bots or link-preview fetchers (WhatsApp, facebookexternalhit, curl...) are not counted.
   - Supabase doesn't forward a country header to functions right now, so `country` is usually null.
3. It sends a **302** to `product_url`, adding `tag=<config.amazon_tag>` (Amazon) or `affid=<config.flipkart_affid>` (Flipkart) when they're set.

### Set the affiliate tag (no redeploy needed)

```sql
update public.config set amazon_tag = 'yourtag-21', updated_at = now() where id;
-- Flipkart: update public.config set flipkart_affid = 'xxxx', updated_at = now() where id;
```

## Adding or updating products (reel pipeline)

**How the bot does it:** run SQL through the Supabase connector (`execute_sql` on project `rrsxsqtfotxkjgkbqnpx`). The service key is never needed locally.

1. On the Mac, run `scripts/add_product.py <job> --product-id <brand-model> --sql` (reel-pipeline stage s8 does this). It writes the image and a local `products.json` entry and **prints** the SQL.
2. Run the printed SQL with `execute_sql`.
3. Run `python3 scripts/export_products.py` so `products.json` is an exact snapshot of `product_cards` (`--check` exits 1 if it's stale).
4. Commit and push the site (new `images/products/<product_id>.webp` + `products.json`).

The SQL looks like this:

```sql
insert into public.products (product_id, title, brand, category, tagline, highlights, image_url, store,
                             store_product_id, product_url, reel_url, featured, sort_order, active)
  values ('oneplus-nord-buds-3r', 'OnePlus Nord Buds 3R TWS Earbuds', 'OnePlus', 'tws_earbuds', null,
          array['12.4mm titanium drivers', '47ms low latency', '54 hours battery', 'dual connection']::text[],
          'images/products/oneplus-nord-buds-3r.webp', 'amazon', 'B0FMDL81GS',
          'https://www.amazon.in/dp/B0FMDL81GS', null, true, 0, true)
  on conflict (product_id) do update set title = excluded.title, ..., active = true, updated_at = now();
insert into public.price_history (product_id, price, listing_price, source)
  values ('oneplus-nord-buds-3r', 1999, null, 'manual');   -- listing_price = MRP only if confirmed
```

To record a new price, run `python3 scripts/record_price.py <product_id> <price> [--mrp N] [--source manual]`. It prints one `insert into public.price_history ...` line for `execute_sql`. Then export + push.

Alternative: `--push` on either script writes over REST. It needs `SUPABASE_SERVICE_ROLE_KEY` exported in your shell. **Never commit that key.** Keep it out of the repo, `config.json` and the site JS. (`export_products.py` only uses the publishable key.)

To hide a product: `update public.products set active = false where product_id = '<id>';` then export + push. It disappears from the site and `/go` returns 404.

### Useful queries

```sql
select product_id, current_price, previous_price, click_count from public.product_cards;
select product_id, count(*), max(clicked_at) from public.clicks group by 1 order by 2 desc;
select product_id, date_trunc('day', clicked_at) d, count(*) from public.clicks group by 1,2 order by 2 desc;
```

## Prices are not live yet

`current_price` is whatever was last recorded (`source = 'manual'` today), and the site shows "Price as of <date>". Options for automatic prices:
- **Amazon PA-API 5:** available once the Associates account has 3 qualifying sales. A daily job then inserts `price_history` rows with `source = 'paapi'`.
- **Keepa API:** paid, works now, `source = 'keepa'`.

Don't scrape Amazon product pages; the Associates terms don't allow it.

## Site wiring

`assets/app.js` paints `products.json` first, and in parallel fetches `/rest/v1/product_cards` with the publishable key (safe in client code); when that lands it re-renders if anything changed (`<html data-source="snapshot|supabase">`). Rows link to `/functions/v1/go?p=<product_id>`. If Supabase is unreachable, the snapshot stays up and links go straight to the store (tag from `config.json`).
