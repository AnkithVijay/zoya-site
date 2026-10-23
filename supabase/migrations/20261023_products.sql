-- Zoya Deals: restructure around `products` (replaces `deals`). Applied 2026-10-23.
-- Tiny dataset (1 product, 1 price row, 0 clicks) -> clean rebuild, preserving the seed
-- price check timestamp. `config` is unchanged.

drop view if exists public.deal_cards;
drop table if exists public.clicks, public.price_history, public.deals cascade;
drop function if exists public.apply_price_check() cascade;
drop function if exists public.bump_click_count() cascade;

create table public.products (
  product_id       text primary key check (product_id ~ '^[a-z0-9][a-z0-9-]{0,80}$'),
  title            text not null,
  brand            text,
  category         text,                          -- reel-pipeline preset key, e.g. tws_earbuds
  tagline          text,                          -- one short line
  highlights       text[] not null default '{}'   -- 0-4 short points shown as one muted line
                   check (cardinality(highlights) <= 4),
  image_url        text,                          -- site-relative (images/products/<id>.webp) or absolute
  store            text not null default 'amazon' check (store in ('amazon','flipkart','other')),
  store_product_id text,                          -- ASIN / Flipkart PID
  product_url      text not null,                 -- clean URL, no affiliate tag (go adds it)
  reel_url         text,                          -- IG / YT link, nullable
  listing_price    numeric(10,2),                 -- MRP; null until confirmed
  current_price    numeric(10,2),                 -- set by price_history trigger
  price_checked_at timestamptz,
  click_count      bigint not null default 0,     -- maintained by trigger on clicks
  featured         boolean not null default false,
  sort_order       integer not null default 0,    -- lower first (after featured)
  active           boolean not null default true,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create table public.price_history (
  id            bigint generated always as identity primary key,
  product_id    text not null references public.products(product_id) on delete cascade on update cascade,
  price         numeric(10,2) not null,
  listing_price numeric(10,2),
  source        text not null default 'manual' check (source in ('manual','paapi','keepa')),
  checked_at    timestamptz not null default now()
);
create index price_history_product_idx on public.price_history (product_id, checked_at desc);

create table public.clicks (
  id         bigint generated always as identity primary key,
  product_id text not null references public.products(product_id) on delete cascade on update cascade,
  clicked_at timestamptz not null default now(),
  referrer   text,
  country    text,
  ua_hash    text                                 -- sha-256 of user agent; no IP stored
);
create index clicks_product_idx on public.clicks (product_id, clicked_at desc);

-- price check -> product prices (only when it is the newest check)
create function public.apply_price_check() returns trigger
language plpgsql set search_path = '' as $$
begin
  update public.products p
     set current_price    = new.price,
         listing_price    = coalesce(new.listing_price, p.listing_price),
         price_checked_at = new.checked_at,
         updated_at       = now()
   where p.product_id = new.product_id
     and (p.price_checked_at is null or p.price_checked_at <= new.checked_at);
  return new;
end $$;
create trigger price_history_apply after insert on public.price_history
  for each row execute function public.apply_price_check();

-- clicks -> products.click_count
create function public.bump_click_count() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    update public.products set click_count = click_count + 1 where product_id = new.product_id;
    return new;
  else
    update public.products set click_count = greatest(click_count - 1, 0) where product_id = old.product_id;
    return old;
  end if;
end $$;
create trigger clicks_count after insert or delete on public.clicks
  for each row execute function public.bump_click_count();
revoke execute on function public.apply_price_check() from public, anon, authenticated;
revoke execute on function public.bump_click_count()  from public, anon, authenticated;

-- What the site reads (and what export_products.py snapshots into products.json)
create view public.product_cards with (security_invoker = true) as
select p.product_id, p.title, p.brand, p.category, p.tagline, p.highlights, p.image_url,
       p.store, p.store_product_id, p.product_url, p.reel_url,
       p.listing_price, p.current_price,
       (select ph.price from public.price_history ph
         where ph.product_id = p.product_id
         order by ph.checked_at desc, ph.id desc offset 1 limit 1) as previous_price,
       p.price_checked_at, p.click_count, p.featured, p.sort_order, p.created_at, p.updated_at
from public.products p
where p.active;

-- RLS + grants (same strictness as before): browser can only SELECT products/price_history/view
alter table public.products      enable row level security;
alter table public.price_history enable row level security;
alter table public.clicks        enable row level security;

create policy "public read active products" on public.products
  for select to anon, authenticated using (active);
create policy "public read history" on public.price_history
  for select to anon, authenticated
  using (exists (select 1 from public.products p where p.product_id = price_history.product_id and p.active));
-- clicks: no policies -> no anon/authenticated access (service role bypasses RLS)

revoke all on public.products, public.price_history, public.clicks, public.product_cards
  from anon, authenticated;
grant select on public.products, public.price_history, public.product_cards to anon, authenticated;

-- Seed (facts from deals.json / reel job product.json / reel caption; MRP, tagline, reel_url unconfirmed -> null)
insert into public.products (product_id, title, brand, category, highlights, image_url, store,
                             store_product_id, product_url, featured, sort_order, created_at)
values ('oneplus-nord-buds-3r', 'OnePlus Nord Buds 3R TWS Earbuds', 'OnePlus', 'tws_earbuds',
        array['12.4mm titanium drivers','47ms low latency','54 hours battery','dual connection'],
        'images/products/oneplus-nord-buds-3r.webp', 'amazon', 'B0FMDL81GS',
        'https://www.amazon.in/dp/B0FMDL81GS', true, 0, '2026-10-23 09:44:41.104295+00');
insert into public.price_history (product_id, price, source, checked_at)
values ('oneplus-nord-buds-3r', 1999, 'manual', '2026-10-23 09:44:41.104295+00');
