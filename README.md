# 7501 Audit

Reconciliation tool for US Customs Form 7501 filings. Given Inditex commercial source TXT and a broker 7501 extract (XLSX), it computes the expected duty stack (MFN + Chapter 99 + cotton fee + MPF), compares to what was filed, and surfaces triaged findings.

Validated against Inditex / Zara entry 113-3957214-9 (Jan 2026): 44/44 lines reconciled, Block 37 duty **$2,503.42** to the cent.

---

## Documentation

| Doc | Audience |
|-----|----------|
| **[USER_MANUAL.md](USER_MANUAL.md)** | **Start here** — sign-in, audit workflow, Dashboard, Reference, CSV export, re-run |
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

Open **http://localhost:5252**, sign in, upload TXT + 7501, click **Run Audit**.

For playground/production, deploys ship through **klearnow/kn-playground** (`applications/inditex-audit-main/`) — merge to `master` triggers the **Inditex Audit Deploy** workflow.

---

## What’s in the app

### Audit view

- Multi-TXT upload (multiple invoices per run)
- Collapsible **Inputs** panel; auto-collapse after run
- Fuzzy invoice matching between TXT and 7501 (audit still runs on mismatch)
- Review tabs: Comparison, Ch99 Stack, Raw, Aggregated, 7501 Filed, Findings, Manufacturer, HTS Consistency
- **Export all (ZIP)** and per-tab **↓ CSV** (respects active filters)
- Save runs to Postgres; browse/load from **Dashboard** (not a tab on the audit page)
- **Update & re-run** on loaded saves (freight/insurance, optional file replace)
- **EU cap branching** for ES/PT/BG — `9903.02.19` vs `9903.02.20` driven by **7501 column 33** MFN rate (≥15% → `.19`, &lt;15% → `.20`)
- **Section 232 stacks** — accepts broker-filed `9903.81.*` / `9903.85.*` and `9903.01.33` exclusion on the same CM item (Info finding, not Critical)
- **232 split adjunct** — separate CM-item 232 lines paired to parent as `232 SPLIT (7501 adjunct)`

### Dashboard

Portfolio analytics, **By Importer** rollup (grouped by CS Importer ID / EIN), runs list (click row to load), import/export JSON, checkbox **bulk delete**, **EU cap affected** filter for re-run checklist

### Reference (authenticated)

Global HTS Classification Table (MFN for duty projection; EU cap branch still uses filed col 33 first), Chapter 99 rules, sources & verification (EU cap + Section 232 callouts), **Re-run all saved audits** (admin — recomputes comparison/findings from stored snapshots)

### Admin

User management, activity log, reference data upload/edit

---

## Repo layout

| File | Purpose |
|------|---------|
| `inditex_audit_dashboard.html` | Single-file UI + audit engine |
| `inditex_audit_server.py` | Flask API, Postgres, auth, reference config |
| `start.sh` | Start Postgres + server + open browser |
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
| Runs | `GET/POST /api/runs`, `GET/PUT/DELETE /api/runs/<id>`, `POST /api/runs/_bulk_delete`, `GET /api/runs/_summary` |
| Reference | `GET /api/reference`, `GET/PUT /api/reference/hts`, `PUT /api/reference/ch99-rules` |
| Users | `GET/POST /api/users`, `PUT /api/users/<u>/password`, `DELETE /api/users/<u>` |
| Activity | `GET/POST /api/activity`, `GET /api/activity/summary` |
| Analytics | `GET /api/analytics/mfn-consistency` |

Full detail in [BUILD.md](BUILD.md).

---

## Out of scope

- Pre-filing validation (post-filing reconciliation only)
- CAPE / PSC refund filing
- Rules auto-update from new EOs — edit reference rules or upload a new HTS table, then re-run audits
