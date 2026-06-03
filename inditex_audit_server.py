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
import secrets
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import msal
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, request, send_file, session
from flask_cors import CORS

# Load .env before reading any os.environ values
load_dotenv(Path(__file__).parent / ".env")

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
# Auth — Microsoft Entra ID (SSO)
# ---------------------------------------------------------------------------
ENTRA_CLIENT_ID     = os.environ.get("ENTRA_CLIENT_ID",     "")
ENTRA_CLIENT_SECRET = os.environ.get("ENTRA_CLIENT_SECRET", "")
# common = any Microsoft org or personal account (multi-tenant)
ENTRA_AUTHORITY     = os.environ.get("ENTRA_AUTHORITY",
                        "https://login.microsoftonline.com/common")
ENTRA_REDIRECT_URI  = os.environ.get("ENTRA_REDIRECT_URI",
                        f"http://localhost:{PORT}/auth/callback")
ENTRA_SCOPES        = ["openid", "profile", "email"]
# Your company's Entra tenant ID — users from this tenant get role='admin'
ADMIN_TENANT_ID     = os.environ.get("ADMIN_TENANT_ID", "")
# Stable secret for Flask session signing; generate once and store in .env
APP_SECRET_KEY      = os.environ.get("APP_SECRET_KEY", secrets.token_hex(32))
# Set DEV_BYPASS_SSO=true to skip Microsoft login during local development
DEV_BYPASS_SSO      = os.environ.get("DEV_BYPASS_SSO", "false").lower() == "true"

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
        # Users table — keyed on Entra object ID (stable across tenants)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            SERIAL PRIMARY KEY,
                entra_oid     TEXT UNIQUE NOT NULL,
                entra_tid     TEXT NOT NULL DEFAULT '',
                email         TEXT NOT NULL DEFAULT '',
                display_name  TEXT NOT NULL DEFAULT '',
                role          TEXT NOT NULL DEFAULT 'user'
                              CHECK (role IN ('admin', 'user')),
                created_at    TIMESTAMPTZ DEFAULT NOW(),
                last_login_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS users_email_idx ON users (email)"
        )
        # Add user_id FK to audit_runs (idempotent — safe to run on existing DB)
        cur.execute("""
            DO $$ BEGIN
                ALTER TABLE audit_runs
                    ADD COLUMN user_id INTEGER REFERENCES users(id);
                CREATE INDEX audit_runs_user_id_idx ON audit_runs (user_id);
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$
        """)
    conn.commit()
    print("  • Schema ready (tables: audit_runs, users)")


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
app.secret_key = APP_SECRET_KEY
app.permanent_session_lifetime = timedelta(days=7)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        ENTRA_CLIENT_ID,
        authority=ENTRA_AUTHORITY,
        client_credential=ENTRA_CLIENT_SECRET,
    )


def _upsert_user(claims: dict) -> dict:
    """Create or update a user row from Entra ID token claims.

    Role logic:
    - New users from the admin tenant (ADMIN_TENANT_ID) start as 'admin'.
    - New users from any other tenant start as 'user'.
    - Existing users keep their current role — manual promotions persist.
    """
    oid   = claims.get("oid") or claims.get("sub", "")
    tid   = claims.get("tid", "")
    email = (claims.get("email") or
             claims.get("preferred_username") or "").lower().strip()
    name  = claims.get("name") or email or "Unknown"
    initial_role = "admin" if (ADMIN_TENANT_ID and tid == ADMIN_TENANT_ID) else "user"

    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO users (entra_oid, entra_tid, email, display_name, role)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (entra_oid) DO UPDATE SET
                    email         = EXCLUDED.email,
                    display_name  = EXCLUDED.display_name,
                    entra_tid     = EXCLUDED.entra_tid,
                    last_login_at = NOW(),
                    updated_at    = NOW()
                RETURNING id, email, display_name, role
            """, (oid, tid, email, name, initial_role))
            user = dict(cur.fetchone())
        conn.commit()
    finally:
        conn.close()
    return user


_DEV_USER = {
    "id": 0, "email": "dev@localhost",
    "display_name": "Dev User (SSO bypassed)",
    "role": "admin", "dev": True,
}


def login_required(f):
    """Decorator that enforces authentication on a route.

    - DEV_BYPASS_SSO=true  → injects a fake admin session, no redirect.
    - API routes (/api/*)   → returns 401 JSON so the browser can handle it.
    - Page routes           → redirects to /login.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if DEV_BYPASS_SSO:
            if "user" not in session:
                session["user"] = _DEV_USER
            return f(*args, **kwargs)
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "Unauthorized",
                    "login_url": "/login",
                }), 401
            session["next_url"] = request.url
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Routes — auth
# ---------------------------------------------------------------------------

@app.route("/login")
def login():
    if DEV_BYPASS_SSO:
        session["user"] = _DEV_USER
        return redirect("/")
    if not ENTRA_CLIENT_ID:
        return Response(
            "<h2 style='font-family:sans-serif'>SSO not configured</h2>"
            "<p style='font-family:sans-serif'>Set <code>ENTRA_CLIENT_ID</code>, "
            "<code>ENTRA_CLIENT_SECRET</code>, and <code>ADMIN_TENANT_ID</code> "
            "in your <code>.env</code> file, then restart.</p>",
            mimetype="text/html", status=503,
        )
    state = secrets.token_urlsafe(16)
    session["auth_state"] = state
    auth_url = _get_msal_app().get_authorization_request_url(
        scopes=ENTRA_SCOPES,
        state=state,
        redirect_uri=ENTRA_REDIRECT_URI,
    )
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    # CSRF check
    if request.args.get("state") != session.pop("auth_state", None):
        return Response(
            "<h2 style='font-family:sans-serif'>Auth state mismatch — "
            "possible CSRF. <a href='/login'>Try again</a>.</h2>",
            status=400, mimetype="text/html",
        )
    error = request.args.get("error")
    if error:
        desc = request.args.get("error_description", "")
        return Response(
            f"<h2 style='font-family:sans-serif'>Login error: {error}</h2>"
            f"<pre>{desc}</pre><a href='/login'>Try again</a>",
            status=400, mimetype="text/html",
        )
    code = request.args.get("code")
    if not code:
        return redirect("/login")

    result = _get_msal_app().acquire_token_by_authorization_code(
        code,
        scopes=ENTRA_SCOPES,
        redirect_uri=ENTRA_REDIRECT_URI,
    )
    if "error" in result:
        return Response(
            f"<h2 style='font-family:sans-serif'>Token error</h2>"
            f"<pre>{result.get('error_description', '')}</pre>"
            f"<a href='/login'>Try again</a>",
            status=400, mimetype="text/html",
        )

    claims = result.get("id_token_claims", {})
    try:
        user = _upsert_user(claims)
    except Exception as e:
        return Response(
            f"<h2 style='font-family:sans-serif'>User sync error</h2><pre>{e}</pre>",
            status=500, mimetype="text/html",
        )

    session["user"] = user
    session.permanent = True
    return redirect(session.pop("next_url", "/"))


@app.route("/logout")
def logout():
    session.clear()
    if DEV_BYPASS_SSO:
        return redirect("/login")
    post_logout = ENTRA_REDIRECT_URI.replace("/auth/callback", "/")
    return redirect(
        f"https://login.microsoftonline.com/common/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={post_logout}"
    )


@app.route("/api/auth/me")
@login_required
def auth_me():
    return jsonify({
        "user":     session.get("user", {}),
        "dev_mode": DEV_BYPASS_SSO,
    })


# ---------------------------------------------------------------------------
# Routes — dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
def upsert_run():
    """Insert or update a run by id (full snapshot in request body)."""
    try:
        snapshot = request.get_json(force=True)
        if not snapshot or not snapshot.get("id"):
            return jsonify({"error": "body must be a snapshot with an id field"}), 400

        fields = _extract_fields(snapshot)
        uid = session.get("user", {}).get("id") or None
        if uid == 0:   # dev-bypass placeholder; no real users row
            uid = None
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_runs (
                    id, name, saved_at, txt_name, xlsx_name,
                    freight, insurance, entry_num, invoice_num, importer,
                    agg_lines, entered_value, total_duty,
                    findings_count, findings_critical, findings_high,
                    data, user_id, created_at, updated_at
                ) VALUES (
                    %(id)s, %(name)s, %(saved_at)s, %(txt_name)s, %(xlsx_name)s,
                    %(freight)s, %(insurance)s, %(entry_num)s, %(invoice_num)s,
                    %(importer)s, %(agg_lines)s, %(entered_value)s, %(total_duty)s,
                    %(findings_count)s, %(findings_critical)s, %(findings_high)s,
                    %(data)s, %(uid)s, NOW(), NOW()
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
            """, {**fields, "data": json.dumps(snapshot), "uid": uid})
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "id": fields["id"]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs/<run_id>", methods=["PUT"])
@login_required
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
@login_required
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
@login_required
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
@login_required
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
