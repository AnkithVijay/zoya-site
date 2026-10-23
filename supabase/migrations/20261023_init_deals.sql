-- Zoya Deals: deals, price history, clicks, config (applied 2026-10-23)

create table public.deals (
  id               text primary key check (id ~ '^[a-z0-9][a-z0-9-]*$'),  -- slug, e.g. nord-buds-3r
  title            text not null,
  store            text not null default 'amazon' check (store in ('amazon','flipkart','other')),
  asin             text,
  product_url      text not null,              -- clean URL, no affiliate tag
  image_url        text,                       -- site-relative (images/deals/x.webp) or absolute
  listing_price    numeric(10,2),              -- MRP / list price (null if unconfirmed)
  current_price    numeric(10,2),
  price_checked_at timestamptz,
  reel_url         text,
  click_count      bigint not null default 0,  -- maintained by trigger on clicks
  active           boolean not null default true,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create table public.price_history (
  id            bigint generated always as identity primary key,
  deal_id       text not null references public.deals(id) on delete cascade,
  price         numeric(10,2) not null,
  listing_price numeric(10,2),
  source        text not null default 'manual' check (source in ('manual','paapi','keepa')),
  checked_at    timestamptz not null default now()
);
create index price_history_deal_idx on public.price_history (deal_id, checked_at desc);

create table public.clicks (
  id         bigint generated always as identity primary key,
  deal_id    text not null references public.deals(id) on delete cascade,
  clicked_at timestamptz not null default now(),
  referrer   text,
  country    text,
  ua_hash    text                               -- sha-256 of user agent; no raw IP / PII
);
create index clicks_deal_idx on public.clicks (deal_id, clicked_at desc);

-- Single-row affiliate config, read only by the `go` edge function (service role)
create table public.config (
  id             boolean primary key default true check (id),
  amazon_tag     text not null default '',
  flipkart_affid text not null default '',
  updated_at     timestamptz not null default now()
);
insert into public.config (id) values (true);

-- New price check -> update the deal's current price (only if it is the newest check)
create or replace function public.apply_price_check() returns trigger
language plpgsql set search_path = '' as $$
begin
  update public.deals d
     set current_price    = new.price,
         listing_price    = coalesce(new.listing_price, d.listing_price),
         price_checked_at = new.checked_at,
         updated_at       = now()
   where d.id = new.deal_id
     and (d.price_checked_at is null or d.price_checked_at <= new.checked_at);
  return new;
end $$;
create trigger price_history_apply after insert on public.price_history
  for each row execute function public.apply_price_check();

-- Keep deals.click_count in sync so the public view never needs to read clicks
create or replace function public.bump_click_count() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    update public.deals set click_count = click_count + 1 where id = new.deal_id;
    return new;
  else
    update public.deals set click_count = greatest(click_count - 1, 0) where id = old.deal_id;
    return old;
  end if;
end $$;
create trigger clicks_count after insert or delete on public.clicks
  for each row execute function public.bump_click_count();
revoke execute on function public.apply_price_check() from public, anon, authenticated;
revoke execute on function public.bump_click_count()  from public, anon, authenticated;

-- Public view the site reads
create view public.deal_cards with (security_invoker = true) as
select d.id, d.title, d.store, d.image_url, d.listing_price, d.current_price,
       d.price_checked_at, d.reel_url, d.created_at,
       (select ph.price from public.price_history ph
         where ph.deal_id = d.id
         order by ph.checked_at desc, ph.id desc offset 1 limit 1) as previous_price,
       d.click_count as total_clicks
from public.deals d
where d.active;

-- RLS + grants: browser (anon/authenticated) can only read deals, price_history, deal_cards
alter table public.deals         enable row level security;
alter table public.price_history enable row level security;
alter table public.clicks        enable row level security;
alter table public.config        enable row level security;

create policy "public read active deals" on public.deals
  for select to anon, authenticated using (active);
create policy "public read history" on public.price_history
  for select to anon, authenticated
  using (exists (select 1 from public.deals d where d.id = deal_id and d.active));
-- clicks / config: no policies -> no access for anon/authenticated (service role bypasses RLS)

revoke all on public.deals, public.price_history, public.clicks, public.config, public.deal_cards
  from anon, authenticated;
grant select on public.deals, public.price_history, public.deal_cards to anon, authenticated;

-- Seed: OnePlus Nord Buds 3R (MRP left null until confirmed from a real source)
insert into public.deals (id, title, store, asin, product_url, image_url)
values ('nord-buds-3r', 'OnePlus Nord Buds 3R TWS Earbuds', 'amazon', 'B0FMDL81GS',
        'https://www.amazon.in/dp/B0FMDL81GS', 'images/deals/oneplus-nord-buds-3r.webp');
insert into public.price_history (deal_id, price, source) values ('nord-buds-3r', 1999, 'manual');
