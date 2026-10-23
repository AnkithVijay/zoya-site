#!/usr/bin/env python3
"""Deprecated alias for add_product.py (products replaced deals on 2026-10-23).

Translates the old flags: --slug/--deal-id -> --product-id, --hot/--not-hot ->
--featured/--not-featured, --date is ignored (created_at is set by the database).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import add_product  # noqa: E402

MAP = {"--slug": "--product-id", "--deal-id": "--product-id", "--hot": "--featured", "--not-hot": "--not-featured"}


def translate(argv):
    out, skip = [], False
    for i, arg in enumerate(argv):
        if skip:
            skip = False
            continue
        key, eq, val = arg.partition("=")
        if key == "--date":
            skip = not eq
            continue
        out.append(MAP.get(key, key) + (eq + val if eq else ""))
    return out


if __name__ == "__main__":
    print("note: add_deal.py is now add_product.py", file=sys.stderr)
    sys.exit(add_product.main(translate(sys.argv[1:])))
