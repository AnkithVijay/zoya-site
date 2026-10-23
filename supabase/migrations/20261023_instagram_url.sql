-- Second reel link: reel_url holds the YouTube Short, instagram_url the Instagram reel (nullable).
alter table public.products add column if not exists instagram_url text;

-- Same view as 20261023_products.sql; only instagram_url appended at the end.
-- CREATE OR REPLACE keeps existing grants; security_invoker restated so it stays on.
create or replace view public.product_cards with (security_invoker = true) as
select p.product_id, p.title, p.brand, p.category, p.tagline, p.highlights, p.image_url,
       p.store, p.store_product_id, p.product_url, p.reel_url,
       p.listing_price, p.current_price,
       (select ph.price from public.price_history ph
         where ph.product_id = p.product_id
         order by ph.checked_at desc, ph.id desc offset 1 limit 1) as previous_price,
       p.price_checked_at, p.click_count, p.featured, p.sort_order, p.created_at, p.updated_at,
       p.instagram_url
from public.products p
where p.active;
