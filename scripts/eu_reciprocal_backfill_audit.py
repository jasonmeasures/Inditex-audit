#!/usr/bin/env python3
"""Read-only audit: re-evaluate EU 9903.02.19/.20 verdicts under corrected mapping + rate date.

Usage:
  python3 scripts/eu_reciprocal_backfill_audit.py [--database inditex_audit]

Requires Postgres (same as inditex_audit_server). Does NOT modify any runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

EU_COUNTRIES = {"BG", "ES", "PT"}
EU_CAP_HIGH = "99030219"
EU_CAP_LOW = "99030220"
EU_THRESHOLD = 15.0


def norm_hts(s: str) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def norm_codes(ch99_str: str) -> set[str]:
    out = set()
    for part in str(ch99_str or "").split(","):
        n = norm_hts(part)
        if n:
            out.add(n)
    return out


def expected_eu_code(mfn_pct: float | None) -> str:
    if mfn_pct is not None and mfn_pct >= EU_THRESHOLD:
        return EU_CAP_HIGH
    return EU_CAP_LOW


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=os.environ.get("DATABASE_URL_DB", "inditex_audit"))
    parser.add_argument("--host", default=os.environ.get("PGHOST", "localhost"))
    parser.add_argument("--user", default=os.environ.get("PGUSER", os.environ.get("USER", "postgres")))
    args = parser.parse_args()

    conn = psycopg2.connect(host=args.host, dbname=args.database, user=args.user)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, name, entry_num, data FROM audit_runs ORDER BY saved_at")
    rows = cur.fetchall()
    conn.close()

    false_positives: list[dict] = []
    false_negatives: list[dict] = []
    it_review: list[dict] = []

    for run in rows:
        data = run["data"] if isinstance(run["data"], dict) else json.loads(run["data"])
        ctx = (data.get("state") or {}).get("ctx") or {}
        filed = (data.get("state") or {}).get("filed") or []
        it_date = ctx.get("itDate")
        rate_date = ctx.get("rateDeterminationDate") or ctx.get("applicableDate")
        entry_date = ctx.get("entryDate")

        if it_date and entry_date and str(it_date)[:10] < str(entry_date)[:10]:
            it_review.append({
                "run_id": run["id"],
                "name": run["name"],
                "entry_num": run.get("entry_num"),
                "it_date": str(it_date)[:10],
                "entry_date": str(entry_date)[:10],
                "rate_date": str(rate_date)[:10] if rate_date else None,
            })

        for f in filed:
            coo = str(f.get("COO") or "").strip().upper()
            if coo not in EU_COUNTRIES:
                continue
            filed_set = norm_codes(f.get("CH99_HTS"))
            if not (EU_CAP_HIGH in filed_set or EU_CAP_LOW in filed_set):
                continue
            mfn = f.get("MFN_RATE_PCT")
            if mfn is not None:
                try:
                    mfn = float(mfn)
                except (TypeError, ValueError):
                    mfn = None
            exp = expected_eu_code(mfn)
            fil = EU_CAP_HIGH if EU_CAP_HIGH in filed_set else EU_CAP_LOW
            item = {
                "run_id": run["id"],
                "name": run["name"],
                "entry_num": run.get("entry_num"),
                "item": f.get("ITEM"),
                "coo": coo,
                "hts": f.get("HTS"),
                "mfn": mfn,
                "filed": fil,
                "expected": exp,
                "rate_date": str(rate_date)[:10] if rate_date else None,
            }
            if fil != exp:
                if fil == EU_CAP_LOW and exp == EU_CAP_HIGH:
                    false_positives.append(item)
                elif fil == EU_CAP_HIGH and exp == EU_CAP_LOW:
                    false_negatives.append(item)

    print(f"Scanned {len(rows)} runs")
    print(f"False positives (broker .20, engine would expect .19): {len(false_positives)}")
    for x in false_positives[:20]:
        print(f"  FP {x['entry_num']} item {x['item']} {x['hts']} mfn={x['mfn']} filed={x['filed']} expected={x['expected']}")
    print(f"False negatives (broker .19 on sub-15% — underpayment risk): {len(false_negatives)}")
    for x in false_negatives[:20]:
        print(f"  FN {x['entry_num']} item {x['item']} {x['hts']} mfn={x['mfn']} filed={x['filed']} expected={x['expected']}")
    print(f"IT date earlier than entry date (manual review): {len(it_review)}")
    for x in it_review[:20]:
        print(f"  IT {x['entry_num']} it={x['it_date']} entry={x['entry_date']} rate={x['rate_date']}")


if __name__ == "__main__":
    main()
