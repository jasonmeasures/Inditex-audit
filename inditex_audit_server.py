#!/usr/bin/env python3
"""
inditex_audit_server.py
-----------------------
Flask + Postgres backend for the 7501 Audit Dashboard.

Serves the dashboard HTML at / and exposes a REST API at /api/* for
persistent run storage. Creates the inditex_audit database and
audit_runs table on first run — no manual DDL required.

Environment variables (all optional, sensible defaults):
    PGHOST       localhost
    PGPORT       5432
    PGUSER       $USER (your OS username)
    PGPASSWORD   (empty — local trust auth)
    PGDATABASE   inditex_audit
    PORT         5252
    HOSTNAME_PRETTY  7501-audit.local
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PGHOST     = os.environ.get("PGHOST",     "localhost")
PGPORT     = int(os.environ.get("PGPORT", "5432"))
PGUSER     = os.environ.get("PGUSER",     os.environ.get("USER", "postgres"))
PGPASSWORD = os.environ.get("PGPASSWORD", "")
PGDATABASE = os.environ.get("PGDATABASE", "inditex_audit")
PORT       = int(os.environ.get("PORT",   "5252"))
HOST_PRETTY = os.environ.get("HOSTNAME_PRETTY", "7501-audit.local")

DASHBOARD_PATH = Path(__file__).parent / "inditex_audit_dashboard.html"

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _connect(database: str) -> psycopg2.extensions.connection:
    kwargs = dict(host=PGHOST, port=PGPORT, user=PGUSER, dbname=database)
    if PGPASSWORD:
        kwargs["password"] = PGPASSWORD
    return psycopg2.connect(**kwargs)


def _ensure_database() -> None:
    """Create inditex_audit database if it doesn't exist."""
    try:
        conn = _connect("postgres")
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (PGDATABASE,)
            )
            exists = cur.fetchone()
            if not exists:
                print(f"  • Database '{PGDATABASE}' not found, creating...")
                cur.execute(f'CREATE DATABASE "{PGDATABASE}"')
                print(f"  • Created database '{PGDATABASE}'")
            else:
                print(f"  • Database '{PGDATABASE}' exists")
        conn.close()
    except Exception as e:
        print(f"  ✗ Could not connect to Postgres: {e}", file=sys.stderr)
        print("    Is Postgres running? Try: brew services start postgresql@16",
              file=sys.stderr)
        sys.exit(1)


def _ensure_schema(conn: psycopg2.extensions.connection) -> None:
    """Create audit_runs table and indexes if they don't exist."""
    ddl = """
    CREATE TABLE IF NOT EXISTS audit_runs (
        id                TEXT PRIMARY KEY,
        name              TEXT NOT NULL,
        saved_at          TIMESTAMP WITH TIME ZONE,
        txt_name          TEXT,
        xlsx_name         TEXT,
        freight           NUMERIC,
        insurance         NUMERIC,
        entry_num         TEXT,
        invoice_num       TEXT,
        importer          TEXT,
        agg_lines         INTEGER,
        entered_value     NUMERIC,
        total_duty        NUMERIC,
        findings_count    INTEGER,
        findings_critical INTEGER,
        findings_high     INTEGER,
        data              JSONB NOT NULL,
        created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS audit_runs_saved_at_idx
        ON audit_runs (saved_at DESC);
    CREATE INDEX IF NOT EXISTS audit_runs_entry_num_idx
        ON audit_runs (entry_num);
    CREATE INDEX IF NOT EXISTS audit_runs_importer_idx
        ON audit_runs (importer);
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    print("  • Schema ready (table: audit_runs)")


def get_conn() -> psycopg2.extensions.connection:
    return _connect(PGDATABASE)


# ---------------------------------------------------------------------------
# Snapshot extraction helpers
# ---------------------------------------------------------------------------

def _extract_fields(snapshot: dict) -> dict:
    """Pull denormalized columns out of a v4 snapshot dict."""
    inputs = snapshot.get("inputs", {})
    state  = snapshot.get("state", {})
    ctx    = state.get("ctx", {})

    saved_at_raw = snapshot.get("savedAt")
    try:
        saved_at = datetime.fromisoformat(saved_at_raw.replace("Z", "+00:00")) if saved_at_raw else None
    except (ValueError, AttributeError):
        saved_at = None

    return {
        "id":                snapshot.get("id"),
        "name":              snapshot.get("name", "Untitled"),
        "saved_at":          saved_at,
        "txt_name":          inputs.get("txtName"),
        "xlsx_name":         inputs.get("xlsxName"),
        "freight":           _to_numeric(inputs.get("freight")),
        "insurance":         _to_numeric(inputs.get("insurance")),
        "entry_num":         ctx.get("entryNum"),
        "invoice_num":       ctx.get("invoice"),
        "importer":          ctx.get("importer"),
        "agg_lines":         _to_int(snapshot.get("aggLines") or len(state.get("agg", []))),
        "entered_value":     _to_numeric(ctx.get("enteredAgg")),
        "total_duty":        _to_numeric(ctx.get("filedCH99")),  # Block 37
        "findings_count":    _to_int(snapshot.get("findingsCount")),
        "findings_critical": _to_int(snapshot.get("findingsCritical")),
        "findings_high":     _to_int(snapshot.get("findingsHigh")),
    }


def _to_numeric(val):
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _to_int(val):
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
CORS(app)  # Wide-open CORS — server is local-only


# ---------------------------------------------------------------------------
# Routes — dashboard
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if DASHBOARD_PATH.exists():
        resp = send_file(str(DASHBOARD_PATH), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp
    return Response(
        "<h1>Dashboard not found</h1>"
        f"<p>Expected: <code>{DASHBOARD_PATH}</code></p>",
        status=404,
        mimetype="text/html",
    )


# ---------------------------------------------------------------------------
# Routes — health
# ---------------------------------------------------------------------------

@app.route("/api/health")
def health():
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM audit_runs")
            run_count = cur.fetchone()[0]
        conn.close()
        return jsonify({
            "ok":       True,
            "backend":  "postgres",
            "database": PGDATABASE,
            "host":     PGHOST,
            "port":     PGPORT,
            "user":     PGUSER,
            "run_count": run_count,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 503


# ---------------------------------------------------------------------------
# Routes — runs
# ---------------------------------------------------------------------------

@app.route("/api/runs", methods=["GET"])
def get_runs():
    """Return all full snapshots, newest first."""
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT data FROM audit_runs ORDER BY saved_at DESC NULLS LAST"
            )
            rows = cur.fetchall()
        conn.close()
        runs = [row["data"] for row in rows]
        return Response(
            json.dumps(runs, default=str),
            mimetype="application/json",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs/_summary", methods=["GET"])
def get_runs_summary():
    """Metadata-only view — no full JSONB payload."""
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, name, entry_num, invoice_num, importer,
                       agg_lines, entered_value, total_duty,
                       findings_count, findings_critical, findings_high,
                       saved_at, created_at, updated_at
                FROM audit_runs
                ORDER BY saved_at DESC NULLS LAST
            """)
            rows = cur.fetchall()
        conn.close()
        return Response(
            json.dumps([dict(r) for r in rows], default=str),
            mimetype="application/json",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs/<run_id>", methods=["GET"])
def get_run(run_id: str):
    """Return one full snapshot by id."""
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT data FROM audit_runs WHERE id = %s", (run_id,))
            row = cur.fetchone()
        conn.close()
        if row is None:
            return jsonify({"error": "not found"}), 404
        return Response(
            json.dumps(row["data"], default=str),
            mimetype="application/json",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs", methods=["POST"])
def upsert_run():
    """Insert or update a run by id (full snapshot in request body)."""
    try:
        snapshot = request.get_json(force=True)
        if not snapshot or not snapshot.get("id"):
            return jsonify({"error": "body must be a snapshot with an id field"}), 400

        fields = _extract_fields(snapshot)
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_runs (
                    id, name, saved_at, txt_name, xlsx_name,
                    freight, insurance, entry_num, invoice_num, importer,
                    agg_lines, entered_value, total_duty,
                    findings_count, findings_critical, findings_high,
                    data, created_at, updated_at
                ) VALUES (
                    %(id)s, %(name)s, %(saved_at)s, %(txt_name)s, %(xlsx_name)s,
                    %(freight)s, %(insurance)s, %(entry_num)s, %(invoice_num)s,
                    %(importer)s, %(agg_lines)s, %(entered_value)s, %(total_duty)s,
                    %(findings_count)s, %(findings_critical)s, %(findings_high)s,
                    %(data)s, NOW(), NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    name              = EXCLUDED.name,
                    saved_at          = EXCLUDED.saved_at,
                    txt_name          = EXCLUDED.txt_name,
                    xlsx_name         = EXCLUDED.xlsx_name,
                    freight           = EXCLUDED.freight,
                    insurance         = EXCLUDED.insurance,
                    entry_num         = EXCLUDED.entry_num,
                    invoice_num       = EXCLUDED.invoice_num,
                    importer          = EXCLUDED.importer,
                    agg_lines         = EXCLUDED.agg_lines,
                    entered_value     = EXCLUDED.entered_value,
                    total_duty        = EXCLUDED.total_duty,
                    findings_count    = EXCLUDED.findings_count,
                    findings_critical = EXCLUDED.findings_critical,
                    findings_high     = EXCLUDED.findings_high,
                    data              = EXCLUDED.data,
                    updated_at        = NOW()
            """, {**fields, "data": json.dumps(snapshot)})
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "id": fields["id"]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs/<run_id>", methods=["PUT"])
def rename_run(run_id: str):
    """Rename a run — updates the name column and the name inside the JSONB blob."""
    try:
        body = request.get_json(force=True)
        new_name = (body or {}).get("name", "").strip()
        if not new_name:
            return jsonify({"error": "name is required"}), 400

        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE audit_runs
                SET name       = %s,
                    data       = jsonb_set(data, '{name}', %s::jsonb),
                    updated_at = NOW()
                WHERE id = %s
            """, (new_name, json.dumps(new_name), run_id))
            if cur.rowcount == 0:
                conn.close()
                return jsonify({"error": "not found"}), 404
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "id": run_id, "name": new_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs/<run_id>", methods=["DELETE"])
def delete_run(run_id: str):
    """Delete one run by id."""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_runs WHERE id = %s", (run_id,))
            deleted = cur.rowcount
        conn.commit()
        conn.close()
        if deleted == 0:
            return jsonify({"error": "not found"}), 404
        return jsonify({"ok": True, "id": run_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs", methods=["DELETE"])
def delete_all_runs():
    """Delete all runs (used by 'Clear all' UI button)."""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_runs")
            deleted = cur.rowcount
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.route("/api/analytics/mfn-consistency")
def mfn_consistency():
    """
    Cross-entry MFN rate consistency check.

    For every (COO, HTS) pair that appears in more than one saved run with
    different MFN rates, return the full list of occurrences sorted by rate
    spread (largest discrepancy first).  Useful for spotting broker
    classification drift or reclassifications over time.
    """
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                WITH filed_items AS (
                    -- One row per filed item; cast MFN_RATE_PCT to numeric.
                    SELECT
                        r.id                                                AS run_id,
                        r.name                                              AS run_name,
                        r.entry_num,
                        r.saved_at,
                        (item->>'COO')                                      AS coo,
                        (item->>'HTS')                                      AS hts,
                        (item->>'MFN_RATE_STR')                             AS mfn_rate_str,
                        ROUND((item->>'MFN_RATE_PCT')::numeric, 4)          AS mfn_rate_pct
                    FROM  audit_runs r,
                          jsonb_array_elements(r.data->'state'->'filed') AS item
                    WHERE (item->>'MFN_RATE_PCT') IS NOT NULL
                      AND (item->>'HTS')          IS NOT NULL
                      AND (item->>'COO')          IS NOT NULL
                ),
                deduped AS (
                    -- One representative row per (run, COO, HTS, rate) so that
                    -- a single entry with 10 items at the same rate doesn't create
                    -- 10 occurrence rows in the output.
                    SELECT DISTINCT ON (run_id, coo, hts, mfn_rate_pct)
                        run_id, run_name, entry_num, saved_at,
                        coo, hts, mfn_rate_str, mfn_rate_pct
                    FROM  filed_items
                    ORDER BY run_id, coo, hts, mfn_rate_pct, mfn_rate_str NULLS LAST
                ),
                discrepancies AS (
                    SELECT
                        coo,
                        hts,
                        count(DISTINCT mfn_rate_pct)                              AS rate_count,
                        array_agg(DISTINCT mfn_rate_pct ORDER BY mfn_rate_pct)    AS rates,
                        max(mfn_rate_pct) - min(mfn_rate_pct)                     AS rate_spread
                    FROM  deduped
                    GROUP BY coo, hts
                    HAVING count(DISTINCT mfn_rate_pct) > 1
                )
                SELECT
                    d.coo,
                    d.hts,
                    d.rate_count,
                    d.rates,
                    ROUND(d.rate_spread, 4)                                        AS rate_spread,
                    json_agg(
                        json_build_object(
                            'run_id',    f.run_id,
                            'run_name',  f.run_name,
                            'entry_num', f.entry_num,
                            'rate',      f.mfn_rate_pct,
                            'rate_str',  f.mfn_rate_str,
                            'saved_at',  f.saved_at
                        )
                        ORDER BY f.mfn_rate_pct, f.saved_at DESC
                    )                                                              AS occurrences
                FROM  discrepancies d
                JOIN  deduped f ON f.coo = d.coo AND f.hts = d.hts
                GROUP BY d.coo, d.hts, d.rate_count, d.rates, d.rate_spread
                ORDER BY d.rate_spread DESC, d.coo, d.hts
            """)
            rows = cur.fetchall()
        conn.close()
        result = []
        for row in rows:
            r = dict(row)
            r["rates"]       = [float(x) for x in (r["rates"] or [])]
            r["rate_spread"] = float(r["rate_spread"]) if r["rate_spread"] is not None else None
            for occ in (r.get("occurrences") or []):
                if occ.get("rate") is not None:
                    occ["rate"] = float(occ["rate"])
            result.append(r)
        return Response(json.dumps(result, default=str), mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pg_url = f"postgres://{PGUSER}@{PGHOST}:{PGPORT}/{PGDATABASE}"
    print("\n📊 Inditex Audit Server")
    print(f"   Database: {pg_url}")
    print(f"   Dashboard: {DASHBOARD_PATH}")

    _ensure_database()

    conn = get_conn()
    _ensure_schema(conn)
    conn.close()

    print(f"\n🚀 Open http://localhost:{PORT} in your browser")
    print("   (Ctrl-C to stop)\n")

    app.run(host="0.0.0.0", port=PORT, debug=False)
