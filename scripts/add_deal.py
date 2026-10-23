#!/usr/bin/env python3
"""Add (or update) a deal on the Zoya Deals site from a reel job folder.

Reads   <job>/product.json   (reel-pipeline schema: title, price{value,mrp}, asin,
        source_url, site, hero_cutout, features)
Writes  <site>/images/deals/<slug>.webp   (hero cutout, trimmed, 640px webp)
        <site>/deals.json                 (upsert by slug, newest first)

Local files only: no git, no deploy, no network.

  python3 scripts/add_deal.py ~/projects/reel-jobs/<slug> \
      [--site ~/projects/zoya-site] [--asin B0XXXXXXXX | --url URL] [--store amazon|flipkart]
      [--price 1999] [--mrp 2999] [--title "..."] [--slug name] [--date YYYY-MM-DD]
      [--reel-url URL] [--hot | --not-hot] [--image path.png] [--dry-run]
"""
import argparse, datetime as dt, json, os, re, sys, tempfile
from pathlib import Path

SITE_DEFAULT = Path(__file__).resolve().parent.parent
ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.I)


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "deal"


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
    """Plain product URL + affiliate placeholder (the site JS fills or strips it)."""
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


def load_deals(path):
    if not path.exists():
        return {"deals": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"deals": data} if isinstance(data, list) else data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", help="reel job folder containing product.json")
    ap.add_argument("--site", default=str(SITE_DEFAULT), help="site folder (default: this repo)")
    ap.add_argument("--slug"); ap.add_argument("--title")
    ap.add_argument("--asin"); ap.add_argument("--url", help="product URL (Amazon or Flipkart)")
    ap.add_argument("--store", choices=["amazon", "flipkart"])
    ap.add_argument("--price"); ap.add_argument("--mrp")
    ap.add_argument("--date", help="YYYY-MM-DD (default today)")
    ap.add_argument("--reel-url"); ap.add_argument("--image", help="override hero image")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--hot", dest="hot", action="store_true", default=None)
    g.add_argument("--not-hot", dest="hot", action="store_false")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    job = Path(a.job).expanduser().resolve()
    pj = job / "product.json"
    if not pj.is_file():
        sys.exit(f"error: {pj} not found")
    product = json.loads(pj.read_text(encoding="utf-8"))
    site = Path(a.site).expanduser().resolve()

    slug = slugify(a.slug or job.name.lstrip("_").removeprefix("smoke-"))
    title = a.title or product.get("title") or slug
    pr = product.get("price") or {}
    price = num(a.price) if a.price else num(pr.get("value") if isinstance(pr, dict) else pr)
    mrp = num(a.mrp) if a.mrp else num(pr.get("mrp") if isinstance(pr, dict) else None)
    src_url = a.url or product.get("source_url")
    store = a.store or store_of(src_url, product.get("site"))
    url = build_url(store, a.asin or product.get("asin"), src_url)
    if not url:
        sys.exit("error: no product URL. Pass --asin B0XXXXXXXX or --url <product url>")
    if price is None:
        sys.exit("error: no price in product.json; pass --price")

    img = find_image(job, product, a.image)
    if not img:
        sys.exit("error: no hero cutout found; pass --image")
    rel_img = f"images/deals/{slug}.webp"

    db_path = site / "deals.json"
    db = load_deals(db_path)
    old = next((d for d in db["deals"] if d.get("slug") == slug), {})
    deal = {
        "slug": slug,
        "title": title,
        "image": rel_img,
        "price": price,
        "store": store,
        "url": url,
        "date": a.date or old.get("date") or dt.date.today().isoformat(),
        "hot": a.hot if a.hot is not None else old.get("hot", False),
    }
    if mrp and mrp > price:
        deal["mrp"] = mrp
    reel = a.reel_url or old.get("reel_url")
    if reel:
        deal["reel_url"] = reel
    feats = [f for f in (product.get("features") or []) if isinstance(f, str)][:4]
    if feats:
        deal["features"] = feats

    db["deals"] = [d for d in db["deals"] if d.get("slug") != slug] + [deal]
    db["deals"].sort(key=lambda d: (d.get("date") or ""), reverse=True)
    db["updated"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    print(("DRY RUN " if a.dry_run else "") + ("updated" if old else "added") + f" {slug}: {title} @ {price} [{store}]")
    print(f"  url   {url}")
    print(f"  image {img} -> {site / rel_img}")
    if a.dry_run:
        print(json.dumps(deal, ensure_ascii=False, indent=2))
        return 0
    to_webp(img, site / rel_img)
    fd, tmp = tempfile.mkstemp(dir=site, suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, db_path)
    print(f"  wrote {db_path} ({len(db['deals'])} deals)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
