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
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import jwt
import psycopg2
import psycopg2.extras
from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

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

JWT_SECRET       = os.environ.get("JWT_SECRET", "change-me-in-production")
JWT_EXPIRES_HOURS = int(os.environ.get("JWT_EXPIRES_HOURS", "8"))

INITIAL_ADMIN_USERNAME = os.environ.get("INITIAL_ADMIN_USERNAME", "admin")
INITIAL_ADMIN_PASSWORD = os.environ.get("INITIAL_ADMIN_PASSWORD", "")

DASHBOARD_PATH = Path(__file__).parent / "inditex_audit_dashboard.html"
APP_BUILD_ID = "2026.06.18-ref-hts"

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


def _ensure_users_schema(conn: psycopg2.extensions.connection) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS users (
        id            SERIAL PRIMARY KEY,
        username      TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role          TEXT NOT NULL CHECK (role IN ('admin', 'collaborator')),
        created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
  ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP WITH TIME ZONE;
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    print("  • Schema ready (table: users)")


def _ensure_reference_schema(conn: psycopg2.extensions.connection) -> None:
    """Global reference data (HTS table, Ch99 rules) shared across all audit runs."""
    ddl = """
    CREATE TABLE IF NOT EXISTS reference_config (
        id                  TEXT PRIMARY KEY,
        filename            TEXT,
        payload             BYTEA,
        code_count          INTEGER,
        json_data           JSONB,
        updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_by          TEXT
    );
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    print("  • Schema ready (table: reference_config)")


def _ensure_activity_schema(conn: psycopg2.extensions.connection) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS user_activity_log (
        id            BIGSERIAL PRIMARY KEY,
        username      TEXT NOT NULL,
        action        TEXT NOT NULL,
        resource_type TEXT,
        resource_id   TEXT,
        detail        JSONB NOT NULL DEFAULT '{}',
        ip_address    TEXT,
        user_agent    TEXT,
        created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS user_activity_log_created_at_idx
        ON user_activity_log (created_at DESC);
    CREATE INDEX IF NOT EXISTS user_activity_log_username_idx
        ON user_activity_log (username, created_at DESC);
    CREATE INDEX IF NOT EXISTS user_activity_log_action_idx
        ON user_activity_log (action);
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    print("  • Schema ready (table: user_activity_log)")


def _log_activity(
    username: str,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict | None = None,
) -> None:
    """Persist a user activity event. Failures are logged but never break the request."""
    try:
        ip = request.remote_addr if request else None
        ua = (request.headers.get("User-Agent", "")[:500] if request else None)
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_activity_log
                    (username, action, resource_type, resource_id, detail, ip_address, user_agent)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                username,
                action,
                resource_type,
                resource_id,
                json.dumps(detail or {}),
                ip,
                ua,
            ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ⚠ Activity log failed ({action}): {e}", file=sys.stderr)


def _seed_initial_admin(conn: psycopg2.extensions.connection) -> None:
    if not INITIAL_ADMIN_PASSWORD:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] > 0:
            return
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
            (INITIAL_ADMIN_USERNAME, generate_password_hash(INITIAL_ADMIN_PASSWORD)),
        )
    conn.commit()
    print(f"  • Seeded initial admin user '{INITIAL_ADMIN_USERNAME}'")


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
# Auth helpers
# ---------------------------------------------------------------------------

def _make_token(username: str, role: str) -> str:
    payload = {
        "sub":  username,
        "role": role,
        "exp":  datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRES_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "missing or invalid Authorization header"}), 401
        try:
            payload = _decode_token(auth_header[7:])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "invalid token"}), 401
        request.current_user = payload
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "missing or invalid Authorization header"}), 401
        try:
            payload = _decode_token(auth_header[7:])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "invalid token"}), 401
        if payload.get("role") != "admin":
            return jsonify({"error": "admin role required"}), 403
        request.current_user = payload
        return f(*args, **kwargs)
    return wrapper


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
        resp.headers["X-App-Build"] = APP_BUILD_ID
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
# Routes — auth
# ---------------------------------------------------------------------------

@app.route("/api/auth/login", methods=["POST"])
def login():
    body = request.get_json(force=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT password_hash, role FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid credentials"}), 401

    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET last_login_at = NOW(), updated_at = NOW() WHERE username = %s",
                (username,),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass

    _log_activity(username, "login", "session", None, {"role": row["role"]})
    token = _make_token(username, row["role"])
    return jsonify({"token": token, "username": username, "role": row["role"]})


@app.route("/api/auth/logout", methods=["POST"])
@require_auth
def logout():
    username = request.current_user.get("sub")
    _log_activity(username, "logout", "session")
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Routes — user management (admin only)
# ---------------------------------------------------------------------------

@app.route("/api/users", methods=["GET"])
@require_admin
def list_users():
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, username, role, created_at, updated_at, last_login_at
                FROM users ORDER BY created_at
            """)
            rows = cur.fetchall()
        conn.close()
        return Response(json.dumps([dict(r) for r in rows], default=str), mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/users", methods=["POST"])
@require_admin
def create_user():
    body = request.get_json(force=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    role = (body.get("role") or "").strip()

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    if role not in ("admin", "collaborator"):
        return jsonify({"error": "role must be 'admin' or 'collaborator'"}), 400

    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                (username, generate_password_hash(password), role),
            )
        conn.commit()
        conn.close()
        _log_activity(
            request.current_user.get("sub"),
            "create_user",
            "user",
            username,
            {"role": role},
        )
        return jsonify({"ok": True, "username": username, "role": role}), 201
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "username already exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<username>/password", methods=["PUT"])
@require_admin
def change_password(username: str):
    body = request.get_json(force=True) or {}
    new_password = body.get("password") or ""
    if not new_password:
        return jsonify({"error": "password is required"}), 400

    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE username = %s",
                (generate_password_hash(new_password), username),
            )
            if cur.rowcount == 0:
                conn.close()
                return jsonify({"error": "user not found"}), 404
        conn.commit()
        conn.close()
        _log_activity(
            request.current_user.get("sub"),
            "change_password",
            "user",
            username,
        )
        return jsonify({"ok": True, "username": username})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/users/<username>", methods=["DELETE"])
@require_admin
def delete_user(username: str):
    if username == request.current_user.get("sub"):
        return jsonify({"error": "cannot delete your own account"}), 400
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE username = %s", (username,))
            if cur.rowcount == 0:
                conn.close()
                return jsonify({"error": "user not found"}), 404
        conn.commit()
        conn.close()
        _log_activity(
            request.current_user.get("sub"),
            "delete_user",
            "user",
            username,
        )
        return jsonify({"ok": True, "username": username})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Routes — runs
# ---------------------------------------------------------------------------

@app.route("/api/runs", methods=["GET"])
@require_auth
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
@require_auth
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
@require_auth
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
@require_auth
def upsert_run():
    """Insert or update a run by id (full snapshot in request body)."""
    try:
        snapshot = request.get_json(force=True)
        if not snapshot or not snapshot.get("id"):
            return jsonify({"error": "body must be a snapshot with an id field"}), 400

        fields = _extract_fields(snapshot)
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM audit_runs WHERE id = %s", (fields["id"],))
            existed = cur.fetchone() is not None
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
        _log_activity(
            request.current_user.get("sub"),
            "save_run",
            "run",
            fields["id"],
            {
                "name": fields["name"],
                "entry_num": fields["entry_num"],
                "importer": fields["importer"],
                "findings_count": fields["findings_count"],
                "is_update": existed,
            },
        )
        return jsonify({"ok": True, "id": fields["id"]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs/<run_id>", methods=["PUT"])
@require_auth
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
        _log_activity(
            request.current_user.get("sub"),
            "rename_run",
            "run",
            run_id,
            {"name": new_name},
        )
        return jsonify({"ok": True, "id": run_id, "name": new_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs/<run_id>", methods=["DELETE"])
@require_auth
def delete_run(run_id: str):
    """Delete one run by id."""
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT name, entry_num, importer FROM audit_runs WHERE id = %s",
                (run_id,),
            )
            row = cur.fetchone()
            cur.execute("DELETE FROM audit_runs WHERE id = %s", (run_id,))
            deleted = cur.rowcount
        conn.commit()
        conn.close()
        if deleted == 0:
            return jsonify({"error": "not found"}), 404
        _log_activity(
            request.current_user.get("sub"),
            "delete_run",
            "run",
            run_id,
            dict(row) if row else {},
        )
        return jsonify({"ok": True, "id": run_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs", methods=["DELETE"])
@require_auth
def delete_all_runs():
    """Delete all runs (used by 'Clear all' UI button)."""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_runs")
            deleted = cur.rowcount
        conn.commit()
        conn.close()
        _log_activity(
            request.current_user.get("sub"),
            "clear_all_runs",
            "run",
            None,
            {"deleted": deleted},
        )
        return jsonify({"ok": True, "deleted": deleted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.route("/api/analytics/mfn-consistency")
@require_auth
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
                    -- One row per 7501 filed line item.
                    SELECT
                        r.id                                                AS run_id,
                        r.name                                              AS run_name,
                        r.entry_num,
                        r.saved_at,
                        (item->>'ITEM')                                     AS item_no,
                        (item->>'MID')                                      AS mid,
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
                discrepancies AS (
                    SELECT
                        coo,
                        hts,
                        count(DISTINCT mfn_rate_pct)                              AS rate_count,
                        array_agg(DISTINCT mfn_rate_pct ORDER BY mfn_rate_pct)    AS rates,
                        max(mfn_rate_pct) - min(mfn_rate_pct)                     AS rate_spread
                    FROM  filed_items
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
                            'item',      f.item_no,
                            'mid',       f.mid,
                            'rate',      f.mfn_rate_pct,
                            'rate_str',  f.mfn_rate_str,
                            'saved_at',  f.saved_at
                        )
                        ORDER BY f.mfn_rate_pct,
                                 NULLIF(regexp_replace(f.item_no, '[^0-9]', '', 'g'), '')::int NULLS LAST,
                                 f.saved_at DESC
                    )                                                              AS occurrences
                FROM  discrepancies d
                JOIN  filed_items f ON f.coo = d.coo AND f.hts = d.hts
                GROUP BY d.coo, d.hts, d.rate_count, d.rates, d.rate_spread
                ORDER BY d.rate_spread DESC, d.coo, d.hts
            """)
            rows = cur.fetchall()
        conn.close()
        _log_activity(request.current_user.get("sub"), "view_mfn_analytics", "analytics")
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
# Routes — activity tracking
# ---------------------------------------------------------------------------

@app.route("/api/activity", methods=["POST"])
@require_auth
def record_activity():
    """Client-reported activity (UI actions not visible to the server alone)."""
    body = request.get_json(force=True) or {}
    action = (body.get("action") or "").strip()
    if not action:
        return jsonify({"error": "action is required"}), 400

    resource_type = (body.get("resource_type") or body.get("resourceType") or None)
    resource_id = body.get("resource_id") or body.get("resourceId")
    detail = body.get("detail") if isinstance(body.get("detail"), dict) else {}

    username = request.current_user.get("sub")
    _log_activity(username, action, resource_type, resource_id, detail)
    return jsonify({"ok": True})


@app.route("/api/activity", methods=["GET"])
@require_auth
def list_activity():
    """Activity log — admins see all users (optional filter); others see only their own."""
    limit = min(int(request.args.get("limit", 5000)), 5000)
    action = (request.args.get("action") or "").strip()
    is_admin = request.current_user.get("role") == "admin"
    username = (request.args.get("username") or "").strip()
    if not is_admin:
        username = request.current_user.get("sub") or ""

    clauses = []
    params: list = []
    if username:
        clauses.append("username = %s")
        params.append(username)
    if action:
        clauses.append("action = %s")
        params.append(action)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT id, username, action, resource_type, resource_id,
                       detail, ip_address, created_at
                FROM user_activity_log
                {where}
                ORDER BY created_at DESC
                LIMIT %s
            """, (*params, limit))
            rows = cur.fetchall()
        conn.close()
        return Response(
            json.dumps([dict(r) for r in rows], default=str),
            mimetype="application/json",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/activity/summary", methods=["GET"])
@require_admin
def activity_summary():
    """Per-user access summary for admins."""
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    u.username,
                    u.role,
                    u.last_login_at,
                    u.created_at,
                    MAX(a.created_at) AS last_activity_at,
                    COUNT(a.id)       AS activity_count
                FROM users u
                LEFT JOIN user_activity_log a ON a.username = u.username
                GROUP BY u.id, u.username, u.role, u.last_login_at, u.created_at
                ORDER BY MAX(a.created_at) DESC NULLS LAST, u.username
            """)
            users = cur.fetchall()

            cur.execute("""
                SELECT action, COUNT(*) AS count
                FROM user_activity_log
                WHERE created_at > NOW() - INTERVAL '30 days'
                GROUP BY action
                ORDER BY count DESC
            """)
            action_counts = cur.fetchall()
        conn.close()
        return Response(
            json.dumps({
                "users": [dict(r) for r in users],
                "action_counts_30d": [dict(r) for r in action_counts],
            }, default=str),
            mimetype="application/json",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Routes — global reference data (admin write, all users read)
# ---------------------------------------------------------------------------

@app.route("/api/reference", methods=["GET"])
@require_auth
def get_reference():
    """Metadata + Ch99 rules. HTS binary is fetched via GET /api/reference/hts."""
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM reference_config WHERE id IN ('hts_table', 'ch99_rules')")
            rows = {r["id"]: dict(r) for r in cur.fetchall()}
        conn.close()

        hts_row = rows.get("hts_table")
        rules_row = rows.get("ch99_rules")
        hts_meta = None
        if hts_row and hts_row.get("payload"):
            hts_meta = {
                "filename": hts_row.get("filename"),
                "codeCount": hts_row.get("code_count"),
                "updatedAt": hts_row.get("updated_at"),
                "updatedBy": hts_row.get("updated_by"),
            }
        rules = rules_row.get("json_data") if rules_row else None
        rules_meta = None
        if rules_row and rules:
            rules_meta = {
                "count": len(rules) if isinstance(rules, list) else 0,
                "updatedAt": rules_row.get("updated_at"),
                "updatedBy": rules_row.get("updated_by"),
            }
        return Response(
            json.dumps({
                "hts": hts_meta,
                "ch99Rules": rules,
                "ch99RulesMeta": rules_meta,
            }, default=str),
            mimetype="application/json",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reference/hts", methods=["GET"])
@require_auth
def get_reference_hts():
    """Download the stored HTS classification table (XLSX bytes)."""
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT filename, payload FROM reference_config WHERE id = 'hts_table'"
            )
            row = cur.fetchone()
        conn.close()
        if not row or not row.get("payload"):
            return jsonify({"error": "HTS table not uploaded"}), 404
        filename = row.get("filename") or "hts_classification_table.xlsx"
        return Response(
            row["payload"],
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reference/hts", methods=["PUT"])
@require_admin
def put_reference_hts():
    """Upload or replace the global HTS classification table."""
    try:
        upload = request.files.get("file")
        if not upload:
            return jsonify({"error": "multipart file field 'file' is required"}), 400
        data = upload.read()
        if not data:
            return jsonify({"error": "empty file"}), 400
        filename = upload.filename or "hts_table.xlsx"
        code_count = request.form.get("codeCount")
        try:
            code_count = int(code_count) if code_count else None
        except ValueError:
            code_count = None
        username = request.current_user.get("sub")
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reference_config (id, filename, payload, code_count, updated_at, updated_by)
                VALUES ('hts_table', %s, %s, %s, NOW(), %s)
                ON CONFLICT (id) DO UPDATE SET
                    filename   = EXCLUDED.filename,
                    payload    = EXCLUDED.payload,
                    code_count = EXCLUDED.code_count,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
            """, (filename, psycopg2.Binary(data), code_count, username))
        conn.commit()
        conn.close()
        _log_activity(
            username,
            "upload_hts_table",
            "reference",
            "hts_table",
            {"filename": filename, "code_count": code_count},
        )
        return jsonify({"ok": True, "filename": filename, "codeCount": code_count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reference/ch99-rules", methods=["PUT"])
@require_admin
def put_reference_ch99_rules():
    """Save the global Chapter 99 rules table."""
    try:
        body = request.get_json(force=True) or {}
        rules = body.get("rules")
        if not isinstance(rules, list):
            return jsonify({"error": "body.rules must be an array"}), 400
        username = request.current_user.get("sub")
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reference_config (id, json_data, code_count, updated_at, updated_by)
                VALUES ('ch99_rules', %s, %s, NOW(), %s)
                ON CONFLICT (id) DO UPDATE SET
                    json_data  = EXCLUDED.json_data,
                    code_count = EXCLUDED.code_count,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
            """, (json.dumps(rules), len(rules), username))
        conn.commit()
        conn.close()
        _log_activity(
            username,
            "save_ch99_rules",
            "reference",
            "ch99_rules",
            {"rule_count": len(rules)},
        )
        return jsonify({"ok": True, "count": len(rules)})
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
    _ensure_users_schema(conn)
    _ensure_activity_schema(conn)
    _ensure_reference_schema(conn)
    _seed_initial_admin(conn)
    conn.close()

    print(f"\n🚀 Open http://localhost:{PORT} in your browser")
    print("   (Ctrl-C to stop)\n")

    app.run(host="0.0.0.0", port=PORT, debug=False)
