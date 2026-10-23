#!/usr/bin/env python3
"""Add (or update) a product on the Zoya Deals site from a reel job folder.

`products` (Supabase, primary key product_id) is the source of truth; products.json in the
site repo is a static snapshot of the public product_cards view that the page paints
instantly, then refreshes from Supabase in the background.

Reads   <job>/product.json   (reel-pipeline schema: title, brand, price{value,mrp}, asin,
        source_url, site, hero_cutout, features, category/category_guess)
Writes  <site>/images/products/<product_id>.webp   (hero cutout, trimmed, 640px webp)
        <site>/products.json                       (snapshot upsert by product_id)

Database (Supabase project rrsxsqtfotxkjgkbqnpx):
  --sql    print idempotent SQL (upsert products + one price_history row). The bot runs it
           through the Supabase connector (execute_sql). This is the default path.
  --push   write to Supabase over REST instead. Needs SUPABASE_SERVICE_ROLE_KEY in the
           environment (never commit it; SUPABASE_URL defaults to the project URL).
After the database write, run scripts/export_products.py to refresh products.json from
Supabase, then commit + push the site. Without --sql/--push nothing leaves the machine.

  python3 scripts/add_product.py ~/projects/reel-jobs/<job> --product-id brand-model \
      [--site ~/projects/zoya-site] [--asin B0XXXXXXXX | --url URL] [--store amazon|flipkart]
      [--price 1999] [--mrp 2999] [--title "..."] [--brand X] [--category tws_earbuds]
      [--tagline "..."] [--highlight "..." (repeat, max 4)] [--reel-url URL]
      [--featured | --not-featured] [--sort-order N] [--image path.png]
      [--source manual|paapi|keepa] [--sql] [--push] [--dry-run]
"""
import argparse, datetime as dt, json, os, re, sys, tempfile, urllib.request
from pathlib import Path

SITE_DEFAULT = Path(__file__).resolve().parent.parent
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://rrsxsqtfotxkjgkbqnpx.supabase.co")
ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.I)


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "product"


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else float(v)
    m = re.sub(r"[^\d.]", "", str(v))
    return num(float(m)) if m else None


def store_of(url, site):
    s = (site or "") + " " + (url or "")
    return "flipkart" if "flipkart" in s.lower() else "amazon"


def build_url(store, asin=None, url=None):
    """Product URL with an affiliate placeholder (clean_url() strips it for the database)."""
    if store == "amazon":
        if not asin and url:
            m = ASIN_RE.search(url)
            asin = m.group(1) if m else None
        if asin:
            return f"https://www.amazon.in/dp/{asin.upper()}/?tag={{AMAZON_TAG}}"
        if url:
            return url.split("?")[0] + "?tag={AMAZON_TAG}"
    if store == "flipkart" and url:
        base = url.split("?")[0]
        pid = re.search(r"[?&]pid=([A-Z0-9]+)", url)
        q = f"pid={pid.group(1)}&" if pid else ""
        return f"{base}?{q}affid={{FLIPKART_AFFID}}"
    return None


def clean_url(url):
    """Product URL for the database: no affiliate params (the go function adds them)."""
    return re.sub(r"[?&](tag|affid)=\{[A-Z_]+\}", "", url).rstrip("/?") if url else url


def q(v):
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"



SNAPSHOT_FIELDS = ["product_id", "title", "brand", "category", "tagline", "highlights", "image_url",
                   "store", "store_product_id", "product_url", "reel_url", "listing_price",
                   "current_price", "previous_price", "price_checked_at", "featured", "sort_order",
                   "created_at"]
DB_COLS = ["product_id", "title", "brand", "category", "tagline", "highlights", "image_url", "store",
           "store_product_id", "product_url", "reel_url", "featured", "sort_order"]


def q_arr(items):
    return "array[" + ", ".join(q(i) for i in items) + "]::text[]" if items else "'{}'::text[]"


def product_sql(row, price, mrp, source):
    """Idempotent upsert + price check. The price_history trigger sets current_price,
    listing_price and price_checked_at on the product."""
    vals = ", ".join(q_arr(row["highlights"]) if c == "highlights" else
                     ("true" if row[c] else "false") if c == "featured" else q(row.get(c)) for c in DB_COLS)
    upd = []
    for c in DB_COLS[1:]:
        if c == "highlights":
            upd.append("highlights = case when cardinality(excluded.highlights) > 0 "
                       "then excluded.highlights else public.products.highlights end")
        elif c in ("featured", "sort_order", "title", "store", "product_url"):
            upd.append(f"{c} = excluded.{c}")
        else:
            upd.append(f"{c} = coalesce(excluded.{c}, public.products.{c})")
    sql = (f"insert into public.products ({', '.join(DB_COLS)}, active)\n  values ({vals}, true)\n"
           f"  on conflict (product_id) do update set {', '.join(upd)}, active = true, updated_at = now();\n")
    if price is not None:
        sql += (f"insert into public.price_history (product_id, price, listing_price, source) "
                f"values ({q(row['product_id'])}, {q(price)}, {q(mrp)}, {q(source)});\n")
    return sql


def rest(path, body, prefer, method="POST"):
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        sys.exit("error: --push needs SUPABASE_SERVICE_ROLE_KEY in the environment (don't commit it)")
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path}", data=json.dumps(body).encode(),
                                 method=method, headers={"apikey": key, "Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json", "Prefer": prefer})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status


def push_rest(row, price, mrp, source):
    body = {k: v for k, v in row.items() if v is not None and v != []}
    body["active"] = True
    print("  supabase products upsert -> " +
          str(rest("products?on_conflict=product_id", body, "resolution=merge-duplicates,return=minimal")))
    if price is not None:
        print("  supabase price_history -> " + str(rest("price_history", {"product_id": row["product_id"],
              "price": price, "listing_price": mrp, "source": source}, "return=minimal")))


def find_image(job, product, override):
    cands = []
    if override:
        cands.append(Path(override).expanduser())
    hc = product.get("hero_cutout")
    if hc:
        p = Path(hc).expanduser()
        cands += [p if p.is_absolute() else job / p, job / "img" / "cut" / p.name]
    for c in product.get("cutouts") or []:
        if c.get("cut"):
            p = Path(c["cut"]).expanduser()
            cands += [p if p.is_absolute() else job / p, job / "img" / "cut" / p.name]
    cands += sorted((job / "img" / "cut").glob("*.png")) if (job / "img" / "cut").is_dir() else []
    for c in cands:
        if c.is_file():
            return c
    return None


def to_webp(src, dst, size=640):
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    bb = im.getchannel("A").getbbox()
    if bb:
        im = im.crop(bb)
    im.thumbnail((int(size * 0.92), int(size * 0.92)), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(im, ((size - im.width) // 2, (size - im.height) // 2))
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, "WEBP", quality=82, method=6)


def load_snapshot(path):
    if not path.exists():
        return {"products": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"products": data} if isinstance(data, list) else data


def write_snapshot(path, snap):
    snap["products"] = sorted(snap["products"], key=lambda p: (not p.get("featured"), p.get("sort_order") or 0,
                              _neg(p.get("created_at"))))
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _neg(ts):
    # newest first inside the same featured/sort_order group
    try:
        return -dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", help="reel job folder containing product.json")
    ap.add_argument("--site", default=str(SITE_DEFAULT), help="site folder (default: this repo)")
    ap.add_argument("--product-id", help="primary key slug, e.g. oneplus-nord-buds-3r (default: from title)")
    ap.add_argument("--title"); ap.add_argument("--brand"); ap.add_argument("--category")
    ap.add_argument("--tagline"); ap.add_argument("--highlight", action="append", help="repeatable, max 4")
    ap.add_argument("--asin"); ap.add_argument("--url", help="product URL (Amazon or Flipkart)")
    ap.add_argument("--store", choices=["amazon", "flipkart"])
    ap.add_argument("--price"); ap.add_argument("--mrp")
    ap.add_argument("--reel-url"); ap.add_argument("--image", help="override hero image")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--featured", dest="featured", action="store_true", default=None)
    g.add_argument("--not-featured", dest="featured", action="store_false")
    ap.add_argument("--sort-order", type=int)
    ap.add_argument("--source", default="manual", choices=["manual", "paapi", "keepa"], help="price source")
    ap.add_argument("--sql", action="store_true", help="print Supabase SQL (run via the connector)")
    ap.add_argument("--push", action="store_true", help="write to Supabase via REST (needs service key env)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    job = Path(a.job).expanduser().resolve()
    pj = job / "product.json"
    if not pj.is_file():
        sys.exit(f"error: {pj} not found")
    product = json.loads(pj.read_text(encoding="utf-8"))
    site = Path(a.site).expanduser().resolve()

    title = a.title or product.get("title")
    if not title:
        sys.exit("error: no title in product.json; pass --title")
    pid = slugify(a.product_id or product.get("product_id") or title)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", pid):
        sys.exit(f"error: bad product_id {pid!r}")
    pr = product.get("price") or {}
    price = num(a.price) if a.price else num(pr.get("value") if isinstance(pr, dict) else pr)
    mrp = num(a.mrp) if a.mrp else num(pr.get("mrp") if isinstance(pr, dict) else None)
    mrp = mrp if (mrp and price and mrp > price) else None
    src_url = a.url or product.get("source_url")
    store = a.store or store_of(src_url, product.get("site"))
    url = build_url(store, a.asin or product.get("asin"), src_url)
    if not url:
        sys.exit("error: no product URL. Pass --asin B0XXXXXXXX or --url <product url>")
    if price is None:
        sys.exit("error: no price in product.json; pass --price")
    store_pid = None
    if store == "amazon":
        m = ASIN_RE.search(url)
        store_pid = (a.asin or product.get("asin") or (m.group(1) if m else None) or "").upper() or None
    elif store == "flipkart":
        m = re.search(r"[?&]pid=([A-Z0-9]+)", url)
        store_pid = m.group(1) if m else None

    img = find_image(job, product, a.image)
    if not img:
        sys.exit("error: no hero cutout found; pass --image")
    rel_img = f"images/products/{pid}.webp"

    snap_path = site / "products.json"
    snap = load_snapshot(snap_path)
    old = next((p for p in snap["products"] if p.get("product_id") == pid), {})
    highlights = [h.strip() for h in (a.highlight or product.get("highlights") or product.get("features") or [])
                  if isinstance(h, str) and h.strip()][:4]
    row = {
        "product_id": pid, "title": title,
        "brand": a.brand or product.get("brand") or old.get("brand"),
        "category": a.category or product.get("category") or product.get("category_guess") or old.get("category"),
        "tagline": a.tagline or product.get("tagline") or old.get("tagline"),
        "highlights": highlights or old.get("highlights") or [],
        "image_url": rel_img, "store": store, "store_product_id": store_pid,
        "product_url": clean_url(url),
        "reel_url": a.reel_url or old.get("reel_url"),
        "featured": a.featured if a.featured is not None else bool(old.get("featured", False)),
        "sort_order": a.sort_order if a.sort_order is not None else int(old.get("sort_order") or 0),
    }
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    entry = {k: row.get(k) for k in SNAPSHOT_FIELDS if k in row}
    entry.update({
        "listing_price": mrp if mrp is not None else old.get("listing_price"),
        "current_price": price,
        "previous_price": old.get("current_price") if old.get("current_price") not in (None, price) else old.get("previous_price"),
        "price_checked_at": now,
        "created_at": old.get("created_at") or now,
    })
    entry = {k: entry.get(k) for k in SNAPSHOT_FIELDS}

    print(("DRY RUN " if a.dry_run else "") + ("updated" if old else "added") + f" {pid}: {title} @ {price} [{store}]")
    print(f"  url   {row['product_url']}")
    print(f"  image {img} -> {site / rel_img}")
    if a.sql:
        print("-- Supabase SQL (run with the connector's execute_sql):")
        print(product_sql(row, price, mrp, a.source))
    if a.dry_run:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0
    if a.push:
        push_rest(row, price, mrp, a.source)
    to_webp(img, site / rel_img)
    snap["products"] = [p for p in snap["products"] if p.get("product_id") != pid] + [entry]
    snap["updated"] = now
    snap["source"] = "local"
    write_snapshot(snap_path, snap)
    print(f"  wrote {snap_path} ({len(snap['products'])} products). "
          "After the DB write, run scripts/export_products.py to resync from Supabase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
