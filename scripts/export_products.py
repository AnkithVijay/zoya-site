#!/usr/bin/env python3
"""OPTIONAL: save a local JSON backup of the public product_cards view.

Not part of the normal workflow. The site no longer reads products.json: app.js fetches
product_cards from Supabase live (with a localStorage cache), so nothing here needs a deploy.
Use this only if you want an offline copy / diff of what the site shows. The output file
(products.json in the repo folder) is git-ignored; don't commit it.

Reads the public product_cards view with the publishable key (read-only; RLS lets anon
see active products only), so no secret is needed.

  python3 scripts/export_products.py [--site ~/projects/zoya-site] [--check]

--check exits 1 if the local backup is out of date (writes nothing).
"""
import argparse, datetime as dt, json, os, sys, tempfile, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_product import SNAPSHOT_FIELDS, SUPABASE_URL, SITE_DEFAULT, num, _neg  # noqa: E402

# Publishable key: same one the site ships; read-only via RLS.
PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_qEE2Mx-rNBreFFh3dJGHrA_886HYX43")


def fetch():
    url = (f"{SUPABASE_URL}/rest/v1/product_cards?select={','.join(SNAPSHOT_FIELDS)}"
           "&order=featured.desc,sort_order.asc,created_at.desc")
    req = urllib.request.Request(url, headers={"apikey": PUBLISHABLE_KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        rows = json.load(r)
    for row in rows:
        for k in ("listing_price", "current_price", "previous_price"):
            row[k] = num(row.get(k))
        row["highlights"] = row.get("highlights") or []
    rows.sort(key=lambda p: (not p.get("featured"), p.get("sort_order") or 0, _neg(p.get("created_at"))))
    return [{k: r.get(k) for k in SNAPSHOT_FIELDS} for r in rows]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=str(SITE_DEFAULT))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    path = Path(a.site).expanduser().resolve() / "products.json"
    rows = fetch()
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if old.get("products") == rows:
        print(f"products.json up to date ({len(rows)} products)")
        return 0
    if a.check:
        print("products.json is out of date; run scripts/export_products.py")
        return 1
    snap = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source": "supabase", "products": rows}
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    print(f"wrote {path} ({len(rows)} products)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
