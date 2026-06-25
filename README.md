# 7501 Audit

Reconciliation tool for US Customs Form 7501 filings. Given Inditex commercial source TXT and a broker 7501 extract (XLSX), it computes the expected duty stack (MFN + Chapter 99 + cotton fee + MPF), compares to what was filed, and surfaces triaged findings.

Validated against Inditex / Zara entry 113-3957214-9 (Jan 2026): 44/44 lines reconciled, Block 37 duty **$2,503.42** to the cent.

---

## Documentation

| Doc | Audience |
|-----|----------|
| **[USER_MANUAL.md](USER_MANUAL.md)** | **Start here** — sign-in, Dashboard, audit workflow, review sign-off, Reference, re-run |
| **[SETUP.md](SETUP.md)** | First-time install (Postgres, venv, `./start.sh`) |
| **[BUILD.md](BUILD.md)** | Architecture and extension guide for developers |

---

## Quick start

```bash
# One-time
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
brew services start postgresql@16

# Set initial admin (first run only) — copy and edit:
# cp .env.example .env

# Every session
./start.sh
```

Open **http://localhost:5252**, sign in — you land on the **Dashboard**. Use **+ New Run** to start an audit.

For playground/production, deploys ship through **klearnow/kn-playground** (`applications/inditex-audit-main/`) — merge to `master` triggers the **Inditex Audit Deploy** workflow.

---

## What’s in the app

### Dashboard (default home)

Opens automatically after sign-in and page refresh. Portfolio analytics, **By Importer** rollup (EIN grouping), runs table with **Issues** preview and **Review** status, expand-row detail and sign-off, filters (including **EU cap affected**). Click a row to load the full audit view.

### Audit view (+ New Run)

- Multi-TXT upload, collapsible **Inputs**, fuzzy invoice matching
- Review tabs: Comparison, Ch99 Stack, Raw, Aggregated, 7501 Filed, Findings, Manufacturer, HTS Consistency
- **Export all (ZIP)** and per-tab **↓ CSV**
- **Reviewer sign-off bar** on loaded runs (same statuses as Dashboard)
- Save runs to Postgres; prior runs open from **Dashboard** only
- **Update & re-run** on loaded saves
- **EU reciprocal** for ES/PT/BG — `9903.02.19` vs `9903.02.20` from **HTSUS Column 1 rate** (HTS table when loaded; ≥15% → `.19`, &lt;15% → `.20`), with **rate-determination date** per 19 CFR 141.68/141.69 (IT Date → release)
- **Section 232 stacks** and **232 split adjunct** handling

### Reference (authenticated)

Global HTS table, Chapter 99 rules, sources & verification, **Recent Activity**, **Run data management** (admin: import/export/clear JSON), **Re-run all saved audits** (admin)

### Admin

User management, activity log (also summarized under Reference → Recent Activity)

---

## Repo layout

| File | Purpose |
|------|---------|
| `inditex_audit_dashboard.html` | Single-file UI + audit engine |
| `inditex_audit_server.py` | Flask API, Postgres, auth, reference config, review sign-off |
| `start.sh` | Start Postgres + server + open browser |
| `verify_eu_reciprocal_rules.py` | Regression tests for EU reciprocal / rate-date logic |
| `scripts/eu_reciprocal_backfill_audit.py` | Read-only audit of historical EU cap verdicts |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |
| `deploy.sh` | Elastic Beanstalk deploy (infra/terraform required) |
| `USER_MANUAL.md` | End-user guide |
| `SETUP.md` | Install walkthrough |
| `BUILD.md` | Developer architecture |

---

## Environment variables

| Var | Default | Notes |
|-----|---------|-------|
| `PGHOST` / `PGPORT` / `PGUSER` / `PGPASSWORD` / `PGDATABASE` | local Postgres | Auto-creates DB on first run |
| `PORT` | `5252` | Flask port |
| `JWT_SECRET` | `change-me-in-production` | **Set in production** |
| `INITIAL_ADMIN_USERNAME` | `admin` | Seeded only when DB has no users |
| `INITIAL_ADMIN_PASSWORD` | *(empty)* | **Set to seed first admin** |

See `.env.example` for a template.

---

## REST API (summary)

Authenticated routes (Bearer token unless noted):

| Area | Endpoints |
|------|-----------|
| Health | `GET /api/health` |
| Auth | `POST /api/auth/login`, `POST /api/auth/logout` |
| Runs | `GET/POST /api/runs`, `GET/PUT/DELETE /api/runs/<id>`, `PATCH /api/runs/<id>/review`, `POST /api/runs/_bulk_delete`, `GET /api/runs/_summary`, `GET /api/runs/_portfolio` |
| Reference | `GET /api/reference`, `GET/PUT /api/reference/hts`, `PUT /api/reference/ch99-rules` |
| Users | `GET/POST /api/users`, `PUT /api/users/<u>/password`, `DELETE /api/users/<u>` |
| Activity | `GET/POST /api/activity`, `GET /api/activity/summary` |
| Analytics | `GET /api/analytics/mfn-consistency` |

Review sign-off statuses: `pending`, `in_progress`, `reviewed`, `needs_deeper_review`, `broker_contacted`, `data_issue`, `waived`.

Full detail in [BUILD.md](BUILD.md).

---

## Verification scripts

```bash
python3 verify_eu_reciprocal_rules.py
python3 scripts/eu_reciprocal_backfill_audit.py   # read-only; requires Postgres
```

---

## Out of scope

- Pre-filing validation (post-filing reconciliation only)
- CAPE / PSC refund filing
- Rules auto-update from new EOs — edit reference rules or upload a new HTS table, then re-run audits
