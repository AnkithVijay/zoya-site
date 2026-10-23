# Zoya Deals: Supabase backend

Project ref: `rrsxsqtfotxkjgkbqnpx` (org "zoya"). API URL: `https://rrsxsqtfotxkjgkbqnpx.supabase.co`

## What's in the database

| Object | What it holds | Browser (anon) access |
|---|---|---|
| `deals` | one row per product: `id` (slug), title, store, asin, `product_url` (clean, no tag), `image_url`, `listing_price` (MRP, null if unconfirmed), `current_price`, `price_checked_at`, `reel_url`, `click_count`, `active` | read (active rows only) |
| `price_history` | every price check: `deal_id`, `price`, `listing_price`, `source` (`manual` / `paapi` / `keepa`), `checked_at` | read |
| `clicks` | one row per "View deal" tap: `deal_id`, `clicked_at`, `referrer`, `country`, `ua_hash` (SHA-256 of the user agent; no IP stored) | none |
| `config` | single row: `amazon_tag`, `flipkart_affid` (read by the `go` function) | none |
| `deal_cards` (view, `security_invoker`) | what the site renders: deal columns + `previous_price` (second-newest check) + `total_clicks` | read |

Triggers:
- inserting into `price_history` updates the deal's `current_price`, `listing_price` (if given) and `price_checked_at` (only if the check is the newest one);
- inserting or deleting `clicks` keeps `deals.click_count` in sync, so the public view never has to read `clicks`.

RLS is on for every table. anon/authenticated have only `SELECT` on `deals`, `price_history` and `deal_cards`.
Every write goes through the service role (the `go` edge function, the Supabase connector, or a script with the service key in env).

Schema source: `migrations/20261023_init_deals.sql` and `migrations/20261023_harden_rls_auto_enable.sql` (both applied).

## Click tracker: `go` edge function

`GET https://rrsxsqtfotxkjgkbqnpx.supabase.co/functions/v1/go?d=<deal_id>`, deployed with `verify_jwt = false`. Source: `functions/go/index.ts`.

1. It looks up the deal with the service role. An unknown or inactive deal returns **404**.
2. It logs a `clicks` row (referrer, country if a geo header is present, `ua_hash`). HEAD requests and obvious bots or link-preview fetchers (WhatsApp, facebookexternalhit, curl...) are not counted.
   - Supabase doesn't forward a country header to functions right now, so `country` is usually null.
3. It sends a **302** to `product_url`, adding `tag=<config.amazon_tag>` (Amazon) or `affid=<config.flipkart_affid>` (Flipkart) when they're set.

### Set the affiliate tag (no redeploy needed)

```sql
update public.config set amazon_tag = 'yourtag-21', updated_at = now() where id;
-- Flipkart: update public.config set flipkart_affid = 'xxxx', updated_at = now() where id;
```

## Adding or updating deals (reel pipeline)

**How the bot does it:** run SQL through the Supabase connector (`execute_sql` on project `rrsxsqtfotxkjgkbqnpx`). The service key is never needed locally.

1. On the Mac, run `scripts/add_deal.py <job> --deal-id <id> --sql`. It writes the image and `deals.json` (the fallback) and **prints** the SQL.
2. Run the printed SQL with `execute_sql`.
3. Commit and push the site so the new `images/deals/<slug>.webp` gets served.

The SQL looks like this:

```sql
insert into public.deals (id, title, store, asin, product_url, image_url, reel_url, active)
values ('nord-buds-3r', 'OnePlus Nord Buds 3R TWS Earbuds', 'amazon', 'B0FMDL81GS',
        'https://www.amazon.in/dp/B0FMDL81GS', 'images/deals/oneplus-nord-buds-3r.webp', null, true)
on conflict (id) do update set title = excluded.title, image_url = excluded.image_url, active = true, updated_at = now();
insert into public.price_history (deal_id, price, listing_price, source)
values ('nord-buds-3r', 1999, null, 'manual');   -- listing_price = MRP only if confirmed
```

To record a new price for an existing deal, run `python3 scripts/record_price.py <deal_id> <price> [--mrp N] [--source manual]`. It prints one `insert into public.price_history ...` line for `execute_sql`.

Alternative: `--push` on either script writes over REST. It needs `SUPABASE_SERVICE_ROLE_KEY` exported in your shell. **Never commit that key.** Keep it out of the repo, `config.json` and the site JS.

To hide a deal, run `update public.deals set active = false where id = '<id>';`. It disappears from the site and `/go` returns 404.

### Useful queries

```sql
select id, current_price, previous_price, total_clicks from public.deal_cards;
select deal_id, count(*), max(clicked_at) from public.clicks group by 1 order by 2 desc;
select deal_id, date_trunc('day', clicked_at) d, count(*) from public.clicks group by 1,2 order by 2 desc;
```

## Prices are not live yet

`current_price` is whatever was last recorded (`source = 'manual'` today), and the site shows "Price as of <date>". Options for automatic prices:
- **Amazon PA-API 5:** available once the Associates account has 3 qualifying sales. A daily job then inserts `price_history` rows with `source = 'paapi'`.
- **Keepa API:** paid, works now, `source = 'keepa'`.

Don't scrape Amazon product pages; the Associates terms don't allow it.

## Site wiring

`assets/app.js` fetches `/rest/v1/deal_cards` with the publishable key, which is safe in client code. If that fails, it falls back to `deals.json` + `config.json`. Rows link to `/functions/v1/go?d=<id>`.
