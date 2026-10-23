#!/usr/bin/env python3
"""Record a price check for an existing Zoya Deals deal in Supabase.

  python3 scripts/record_price.py nord-buds-3r 1799 [--mrp 2499] [--source manual|paapi|keepa] [--push]

Prints SQL for the Supabase connector (execute_sql) by default. --push writes over REST
and needs SUPABASE_SERVICE_ROLE_KEY in the environment (never commit it).
The price_history trigger updates deals.current_price / listing_price / price_checked_at,
and the site's deal_cards view picks up the change marker (previous_price) automatically.
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_deal import num, q, SUPABASE_URL  # noqa: E402
import json, os, urllib.request  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("deal_id"); ap.add_argument("price")
    ap.add_argument("--mrp"); ap.add_argument("--source", default="manual", choices=["manual", "paapi", "keepa"])
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args(argv)
    price, mrp = num(a.price), num(a.mrp)
    if price is None:
        sys.exit("error: bad price")
    mrp = mrp if (mrp and mrp > price) else None
    sql = (f"insert into public.price_history (deal_id, price, listing_price, source) "
           f"values ({q(a.deal_id)}, {q(price)}, {q(mrp)}, {q(a.source)});")
    print(sql)
    if a.push:
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or sys.exit("error: set SUPABASE_SERVICE_ROLE_KEY")
        body = {"deal_id": a.deal_id, "price": price, "listing_price": mrp, "source": a.source}
        req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/price_history", data=json.dumps(body).encode(),
                                     method="POST", headers={"apikey": key, "Authorization": f"Bearer {key}",
                                     "Content-Type": "application/json", "Prefer": "return=minimal"})
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"pushed ({r.status})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
