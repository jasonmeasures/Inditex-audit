#!/usr/bin/env python3
"""Regression tests for EU reciprocal (9903.02.19 / 9903.02.20) and rate-determination date logic.

MFN for the EU cap branch is the true HTSUS Column 1 rate (HTS table when loaded in the
dashboard; broker col 33 is fallback only). Mirrors inditex_audit_dashboard.html helpers.
Run: python3 verify_eu_reciprocal_rules.py
"""

from __future__ import annotations

EU_RECIPROCAL_START = "2025-08-07"
EU_RECIPROCAL_IN_TRANSIT_ENTER_BY = "2025-10-05"
EU_RECIPROCAL_PRIOR_CODE = "9903.01.25"
EO14389_REVIEW_FROM = "2026-02-20"
EU_CAP_THRESHOLD = 15.0
EU_CAP_CODE_HIGH = "9903.02.19"
EU_CAP_CODE_LOW = "9903.02.20"
EU_COUNTRIES = {"BG", "ES", "PT"}


def resolve_rate_determination_date(fields: dict) -> dict:
    missing: list[str] = []

    def iso(v):
        if v is None or v == "":
            return None
        s = str(v).strip()[:10]
        return s if len(s) == 10 else None

    it = iso(fields.get("itDate"))
    if it:
        return {"date": it, "source": "it", "missing": missing}

    entry_type = str(fields.get("entryType") or "").lower()
    if "31" in entry_type or "warehouse withdrawal" in entry_type:
        wd = iso(fields.get("warehouseWithdrawalDate")) or iso(fields.get("entryDate"))
        if wd:
            return {"date": wd, "source": "warehouse_withdrawal", "missing": missing}
        missing.append("warehouse_withdrawal_date")

    oc = iso(fields.get("overcarriedOriginalEntryDate"))
    if oc:
        return {"date": oc, "source": "overcarried_original", "missing": missing}

    release = iso(fields.get("latestReleaseDate"))
    if release:
        return {"date": release, "source": "release", "missing": missing}

    entry = iso(fields.get("entryDate"))
    if entry:
        missing.append("latest_release_date")
        return {"date": entry, "source": "entry_fallback", "missing": missing}

    imp = iso(fields.get("importDate"))
    if imp:
        return {"date": imp, "source": "import_fallback", "missing": missing}

    return {"date": "2099-01-01", "source": "today", "missing": missing}


def is_in_transit_grandfathered(fields: dict, rate_date: str) -> bool:
    export_date = str(fields.get("exportDate") or "")[:10] or None
    if not export_date or not rate_date:
        return False
    return export_date < EU_RECIPROCAL_START and rate_date < EU_RECIPROCAL_IN_TRANSIT_ENTER_BY


def resolve_eu_layer(mfn_pct: float | None) -> tuple[str, float]:
    use_high = mfn_pct is not None and mfn_pct >= EU_CAP_THRESHOLD
    if use_high:
        return EU_CAP_CODE_HIGH, 0.0
    return EU_CAP_CODE_LOW, 15.0


def expected_eu_ch99(mfn_pct: float | None, rate_date: str, in_transit: bool = False) -> dict:
    if rate_date >= EO14389_REVIEW_FROM:
        return {"ch99": "—", "review_code": "NEEDS_REVIEW_EO14389"}
    if in_transit or rate_date < EU_RECIPROCAL_START:
        return {"ch99": EU_RECIPROCAL_PRIOR_CODE, "rate_pct": 10.0}
    ch99, rate = resolve_eu_layer(mfn_pct)
    return {"ch99": ch99, "rate_pct": rate}


def assert_eq(label: str, got, want):
    if got != want:
        raise AssertionError(f"{label}: got {got!r}, want {want!r}")


def main() -> None:
    # Truth table
    ch99, rate = resolve_eu_layer(0.0)
    assert_eq("Free → .20", ch99, EU_CAP_CODE_LOW)
    assert_eq("Free rate", rate, 15.0)

    ch99, rate = resolve_eu_layer(2.5)
    assert_eq("2.5% → .20", ch99, EU_CAP_CODE_LOW)

    ch99, rate = resolve_eu_layer(15.0)
    assert_eq("15% → .19", ch99, EU_CAP_CODE_HIGH)
    assert_eq("15% reciprocal", rate, 0.0)

    ch99, rate = resolve_eu_layer(20.0)
    assert_eq("20% → .19", ch99, EU_CAP_CODE_HIGH)

    # Rate-determination date priority
    r = resolve_rate_determination_date({
        "itDate": "2025-07-20",
        "entryDate": "2025-08-20",
        "latestReleaseDate": "2025-08-20",
    })
    assert_eq("IT wins", r["source"], "it")
    assert_eq("IT date", r["date"], "2025-07-20")

    r = resolve_rate_determination_date({
        "entryType": "31 Warehouse Withdrawal",
        "warehouseWithdrawalDate": "2025-08-10",
        "entryDate": "2025-07-01",
    })
    assert_eq("warehouse source", r["source"], "warehouse_withdrawal")
    assert_eq("warehouse date", r["date"], "2025-08-10")

    r = resolve_rate_determination_date({
        "latestReleaseDate": "2026-01-16",
        "entryDate": "2026-01-16",
    })
    assert_eq("release default", r["source"], "release")
    assert_eq("release date", r["date"], "2026-01-16")

    # IT carve-out: pre-effective rate date → not 9903.02.x
    exp = expected_eu_ch99(0.0, "2025-07-20")
    assert_eq("pre-effective code", exp["ch99"], EU_RECIPROCAL_PRIOR_CODE)

    # Perfume case: ES Free, 2026-01-16
    exp = expected_eu_ch99(0.0, "2026-01-16")
    assert_eq("perfume ch99", exp["ch99"], EU_CAP_CODE_LOW)

    # EO14389 review
    exp = expected_eu_ch99(0.0, "2026-03-01")
    assert_eq("EO14389", exp.get("review_code"), "NEEDS_REVIEW_EO14389")

    # In-transit grandfather
    fields = {"exportDate": "2025-08-01", "entryDate": "2025-09-01"}
    rd = resolve_rate_determination_date(fields)
    in_transit = is_in_transit_grandfathered(fields, rd["date"])
    assert_eq("in-transit flag", in_transit, True)
    exp = expected_eu_ch99(0.0, rd["date"], in_transit)
    assert_eq("in-transit code", exp["ch99"], EU_RECIPROCAL_PRIOR_CODE)

    # China regression (not EU — sanity that EU set is narrow)
    assert_eq("CN not EU", "CN" in EU_COUNTRIES, False)

    print("OK — all EU reciprocal / rate-date regression checks passed")


if __name__ == "__main__":
    main()
