# 7501 Audit Tool — Build & Architecture Guide

This document is the source-of-truth for an AI coding assistant (Cursor, Claude Code, etc.) or a new developer to understand, rebuild, run, or extend the Inditex 7501 broker audit tool. Read top-to-bottom in one pass.

---

## 1. What this tool does

Customs brokers file CBP Form 7501 ("Entry Summary") to declare imported goods and pay duty. Importers send the broker a commercial data file (the TXT) before each shipment so the broker can prepare the entry. **This tool reconciles the two**: it parses both the importer's source TXT and the broker's filed 7501 (exported as Excel), then surfaces discrepancies — incorrect Chapter 99 tariff stacks, wrong MIDs, missing line items, miscalculated entered values, and so on.

Specifically built for Inditex (Zara's parent) shipments, but the engine is generic over any importer who follows the same TXT layout.

Concrete example: a Zara entry of 113-3957214-9 has 389 raw TXT lines that aggregate to 44 unique COO+HTS+MID groups. The 7501 should have 44 filed items matching those groups, with Block 37 (total duty) of $2,503.42. The tool confirms all 44 matched, finds 5 with loose-match MID typos worth flagging, and surfaces 8 entered-value rounding diffs.

---

## 2. Architecture at a glance

```
┌────────────────────────────────┐                ┌──────────────────────────┐
│ Browser (Chrome, Safari, …)    │                │ Local machine            │
│  ┌──────────────────────────┐  │                │  ┌────────────────────┐  │
│  │ inditex_audit_dashboard  │  │                │  │ inditex_audit_     │  │
│  │   .html (single file)    │  │ HTTP            │  │   server.py        │  │
│  │   - All parsing logic    │◀─┼─localhost:5252─▶│  │   (Flask)          │  │
│  │   - UI                   │  │ /api/runs       │  │                    │  │
│  │   - Rules engine         │  │ /api/health     │  │                    │  │
│  └──────────────────────────┘  │                │  └─────────┬──────────┘  │
└────────────────────────────────┘                │            │ psycopg2    │
                                                  │            ▼             │
                                                  │  ┌────────────────────┐  │
                                                  │  │ PostgreSQL 16      │  │
                                                  │  │   inditex_audit    │  │
                                                  │  │     .audit_runs    │  │
                                                  │  └────────────────────┘  │
                                                  └──────────────────────────┘
```

Three components, all run locally:

1. **`inditex_audit_dashboard.html`** — single self-contained file. ~3,500 lines, ~160 KB. Includes all HTML, CSS, and JS. All parsing, the rules engine, and the UI live here. Opens directly in a browser; works offline.
2. **`inditex_audit_server.py`** — Flask server (~375 lines). Serves the dashboard at `/` and exposes a REST API at `/api/*` for persistent saves. Spins up Postgres tables on first run.
3. **PostgreSQL 16** — local database. One table (`audit_runs`) with JSON snapshots + denormalized columns for SQL queries.

The dashboard auto-detects backend at page load by probing `/api/health`. Three modes, picked automatically:

| Mode | When | Persistent? |
|---|---|---|
| **Postgres** | Flask server reachable on the URL the dashboard is loaded from | ✅ Yes, unlimited |
| **localStorage** | Dashboard loaded over `http://` but no server | ✅ Yes, but ~5 MB cap |
| **In-memory** | Dashboard loaded via `file://` (Chrome blocks localStorage there) | ❌ Lost on refresh |

---

## 3. File layout

A working install looks like this:

```
~/Inditex-audit-main/
├── inditex_audit_dashboard.html   ← single-file UI + audit engine (~8,600 lines)
├── inditex_audit_server.py        ← Flask + Postgres + auth + reference API (~1,200 lines)
├── start.sh                       ← local dev launcher (Postgres + Flask + browser)
├── requirements.txt
├── .env.example
├── USER_MANUAL.md                 ← end-user guide (audit, dashboard, reference)
├── SETUP.md                       ← install walkthrough
├── BUILD.md                       ← this file
├── README.md                      ← repo overview
├── deploy.sh                      ← EB deploy (needs terraform init)
└── terraform/                     ← infra modules (owner-managed)
```

---

## 4. The dashboard — `inditex_audit_dashboard.html`

### 4.1 Sections of the file

Single-file HTML organized roughly as:

| Lines | Contents |
|---|---|
| 1–10 | DOCTYPE + html head |
| 11–620 | `<style>` block — KlearNow Engine design tokens, layout, components |
| 621–870 | `<body>` markup — tabs, KPI grid, filter bars, table containers |
| 871–950 | External script tags (SheetJS for XLSX parsing) |
| 951–end | Inline `<script>` — all parsing, rules, UI logic |

### 4.2 Design tokens (KlearNow Engine)

CSS variables at the top of `<style>`:

```css
--primary-700: #003F5B;      /* deep blue, brand primary */
--primary-500: #005D7C;      /* sapphire */
--marigold-500: #F69000;     /* accent orange */
--marigold-700: #B06604;     /* dark marigold */
--green-700: #047857;        /* success */
--red-700: #B42B23;          /* danger */
--gray-50/100/.../900        /* neutrals */
--font-body: Inter, system-ui, sans-serif
--font-mono: 'JetBrains Mono', monospace
```

Inter loaded from Google Fonts via `<link>` in head. JetBrains Mono is local fallback.

### 4.3 JS modules (logical groupings, all in one script tag)

In top-to-bottom order:

| Topic | Key functions |
|---|---|
| **Constants** | `MPF_RATE = 0.003464`, `COTTON_FEE_RATES`, `EU_COUNTRIES = {"ES","PT"}`, `DEFAULT_CH99_RULES` (77 rules) |
| **TXT parser** | `parseInditexTxt(buf)` — reads UTF-16-LE tab-delimited file, returns row objects |
| **XLSX parser** | `parse7501Xlsx(buf)` — reads broker's 7501 export, handles old + new banner-row format, normalizes COO strays |
| **Rules engine** | `expectedChapter99(country, hts, mfnPct, rules)` — returns stack of Ch99 layers for a line. `rulesInEffectOn(rules, isoDate)` filters by effective date. `resolveApplicableDate(entryDate, importDate)` picks the date to use |
| **Aggregation** | `aggregateMethodB(txt)` — groups TXT rows by COO+HTS+MID. `allocateCharges(rows, basis, total, freight, insurance)` — pro-rates freight/insurance |
| **7501 build** | `build7501Filed(xl)` — collapses 7501's multi-row-per-item structure into one row per item with computed AVD / Cotton / MPF |
| **Comparison** | `compareAggToFiled(agg, filed, rules)` — produces `cmp` rows with MATCH / MID_CHECK / CH99_CHECK |
| **Findings** | `buildFindings(cmp, ctx)` — generates severity-ranked finding cards, rolled up at >10 per category |
| **Snapshot/store** | `snapshotCurrentRun(name)` — slim serializable snapshot. `rehydrateRun(r)` — re-inflate on load. `runStore` IIFE — three-backend abstraction (Postgres / localStorage / memory) |
| **Renderers** | `renderKpis`, `renderRecon`, `renderCmp`, `renderStack`, `renderRaw`, `renderAgg`, `renderFiled`, `renderFindings`, `renderHTSConsistency`, `renderRules`, `renderVerify`, `renderRuns` |
| **UI wiring** | DOM event listeners, tab switching, save/import/export, file upload handlers |

### 4.4 Snapshot schema (current: v4)

When the user saves a run, this is what gets stored in localStorage or POSTed to the server:

```js
{
  id: "run_<timestamp>_<rand6>",
  name: "Entry 113-... · Invoice ... · 2026-05-28",
  savedAt: "2026-05-28T13:00:00.000Z",
  schemaVersion: 4,
  rawDropped: true,         // raw lines dropped to fit 500 KB budget
  rawRowCount: 2916,        // for empty-state messaging
  findingsCount: 36,        // lightweight count (full findings rebuilt on load)
  findingsCritical: 11,
  findingsHigh: 9,
  inputs: { txtName, xlsxName, freight, insurance },
  state: {
    raw: [],                // dropped when too large
    agg: [...282 lines...],
    filed: [...282 items...],
    ctx: {
      entryNum, invoice, invoiceFiled, importer,
      applicableDate: "2026-01-17",
      applicableDateSource: "import",   // "entry" | "import" | "today"
      entryDate, importDate,
      effectiveRulesCount: 77, totalRulesCount: 77,
      enteredAgg, enteredFiled, filedMFN, filedCH99, filedMPF, filedCotton,
      strictMatched, looseMatched, noMatch, midMismatch, ch99Mismatch,
      dupesPrimary: []      // 7501 extract defects
    },
    rules: [...]            // copy of rules used at audit time
  }
  // NOTE: state.cmp and state.findings are intentionally NOT stored — they get
  // rebuilt on load via compareAggToFiled() + buildFindings(). Keeps snapshot small.
}
```

Slim-snapshot sizes in practice:
- Zara entry (389 raw lines): ~28 KB
- Big new entry (2,916 raw lines): ~148 KB (raw dropped to fit 500 KB budget)

### 4.5 Storage backend abstraction

`runStore` is a closure exposing:

```js
runStore.backend                 // "postgres" | "localStorage" | "memory"
await runStore.init()            // probes /api/health, switches to postgres if available
runStore.get()                   // returns serialized runs array (string)
runStore.set(jsonString)         // writes; in postgres mode diffs against cache and POSTs deltas
runStore.bytesUsed()             // current footprint
await runStore.deleteRun(id)     // mode-aware delete
await runStore.renameRun(id, n)  // mode-aware rename
await runStore.clearAll()        // wipes everything
```

LocalStorage mode includes auto-prune on `QuotaExceededError` — evicts the oldest runs until the new one fits.

### 4.6 UI structure

**Top-level views** (overlays toggled from the header; audit is the default `page`):

| View | ID / overlay | Auth | Purpose |
|------|----------------|------|---------|
| **Audit** | `.page` | Optional for run; save needs server | Upload TXT/XLSX, review results, save run |
| **Dashboard** | `#dashOverlay` | Required | Saved runs list, portfolio analytics, import/export, bulk delete |
| **Reference** | `#referenceOverlay` | Required | HTS table, Ch99 rules, sources & verification, re-run all (admin) |
| **Users** | `#usersOverlay` | Admin | User CRUD |
| **Activity** | `#activityOverlay` | Admin | Activity log + summary |

**Audit results — review tabs** (left-to-right):

1. **Comparison** — main reconciliation table (MATCH / MID / CH99 badges)
2. **Ch99 Stack** — expected tariff stack per line
3. **Raw Lines** — TXT rows with computed duty
4. **Aggregated** — Method B (COO+HTS+MID) groups
5. **7501 Filed** — broker filed rows
6. **Findings** — severity-ranked cards
7. **Manufacturer** — MID rollup for current entry
8. **HTS Consistency** — within-entry + rules baseline; cross-run HTS is on Dashboard

**CSV export:** per-tab `↓ CSV` (filtered grid) + **Export all (ZIP)** above tabs.

**Inputs** panel is collapsible (`setInputsCollapsed`); auto-collapses after run/load.

**Saved runs** are loaded from Dashboard (`loadRunByIdAsync`) — not a tab on the audit page.

KPI grid: Raw lines · Filed items · Matched · Entered value · Filed duty · Fees · Ch99 rules as of · Findings.

---

## 5. The server — `inditex_audit_server.py`

### 5.1 What it does

- Serves `inditex_audit_dashboard.html` at `/`
- Exposes REST API at `/api/*` for run persistence
- Creates the `inditex_audit` database and `audit_runs` table on first run (no manual DDL needed)
- Reads connection params from env vars with sensible defaults

### 5.2 Configuration (env vars, all optional)

```bash
PGHOST=localhost
PGPORT=5432
PGUSER=<your-OS-user>
PGPASSWORD=
PGDATABASE=inditex_audit
PORT=5252
HOSTNAME_PRETTY=7501-audit.local
JWT_SECRET=change-me-in-production
JWT_EXPIRES_HOURS=8
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=      # set to seed first admin when users table is empty
```

See `.env.example`. `start.sh` sources `.env` when present.

### 5.3 Schema

Additional tables (created on startup): `users`, `reference_config` (HTS JSON + Ch99 rules), `activity_log`.

```sql
CREATE TABLE audit_runs (
    id                TEXT PRIMARY KEY,        -- run_<ts>_<rand6>
    name              TEXT NOT NULL,
    saved_at          TIMESTAMP WITH TIME ZONE,
    txt_name          TEXT,
    xlsx_name         TEXT,
    freight           NUMERIC,
    insurance         NUMERIC,
    entry_num         TEXT,                    -- for SQL filter/sort
    invoice_num       TEXT,
    importer          TEXT,
    agg_lines         INTEGER,
    entered_value     NUMERIC,
    total_duty        NUMERIC,
    findings_count    INTEGER,
    findings_critical INTEGER,
    findings_high     INTEGER,
    data              JSONB NOT NULL,          -- full snapshot
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX audit_runs_saved_at_idx  ON audit_runs (saved_at DESC);
CREATE INDEX audit_runs_entry_num_idx ON audit_runs (entry_num);
CREATE INDEX audit_runs_importer_idx  ON audit_runs (importer);
```

### 5.4 REST endpoints

Most `/api/*` routes require `Authorization: Bearer <jwt>` from `POST /api/auth/login`. Exceptions: `GET /`, `GET /api/health`, `POST /api/auth/login`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | — | Serves dashboard HTML |
| GET | `/api/health` | — | DB connectivity + run count |
| POST | `/api/auth/login` | — | Returns JWT |
| POST | `/api/auth/logout` | user | End session |
| GET | `/api/runs` | user | Full snapshots |
| GET | `/api/runs/_summary` | user | Metadata-only list |
| GET | `/api/runs/<id>` | user | Single snapshot |
| POST | `/api/runs` | user | Upsert run |
| PUT | `/api/runs/<id>` | user | Rename |
| DELETE | `/api/runs/<id>` | user | Delete one |
| POST | `/api/runs/_bulk_delete` | user | Body `{ids: [...]}` |
| DELETE | `/api/runs` | user | Delete all |
| GET | `/api/reference` | user | HTS + Ch99 rules bundle |
| GET/PUT | `/api/reference/hts` | user / admin | HTS table |
| PUT | `/api/reference/ch99-rules` | admin | Save rules |
| GET/POST | `/api/users` | admin | List / create users |
| PUT | `/api/users/<u>/password` | admin | Reset password |
| DELETE | `/api/users/<u>` | admin | Delete user |
| GET/POST | `/api/activity` | admin | Activity log |
| GET | `/api/activity/summary` | admin | Aggregates |
| GET | `/api/analytics/mfn-consistency` | user | Cross-run MFN analytics |

CORS is open for local/dev. Set `JWT_SECRET` and `INITIAL_ADMIN_PASSWORD` in production.

### 5.5 Server behavior

- Connects to the default `postgres` database first, runs `CREATE DATABASE inditex_audit` if missing, then reconnects to it
- Idempotent schema creation on every startup
- Binds to `0.0.0.0` so a custom hostname (`7501-audit.local` via `/etc/hosts`) resolves
- Logs each request to stdout (Flask default)

---

## 6. Setup & first run

### macOS (target environment)

```bash
brew install postgresql@16
brew services start postgresql@16
cd ~/Inditex-audit-main
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # set INITIAL_ADMIN_PASSWORD, JWT_SECRET
./start.sh
```

You'll see:

```
📊 Inditex Audit Server
   Database: postgres://<user>@localhost:5432/inditex_audit
   Dashboard: ./inditex_audit_dashboard.html
  • Database 'inditex_audit' not found, creating...
  • Created database 'inditex_audit'
  • Schema ready (table: audit_runs)

🚀 Open http://localhost:5252 in your browser
```

Open `http://localhost:5252`, sign in, and confirm **Dashboard** loads. See [USER_MANUAL.md](USER_MANUAL.md) for workflow.

### Linux

Same as macOS but replace step 1 with:

```bash
sudo apt install postgresql-16 postgresql-client-16
sudo service postgresql start
sudo -u postgres createuser -s $USER   # one-time: give your user superuser
```

### Windows

Install Postgres via the EnterpriseDB installer, install Python from python.org, then steps 2–3 are identical.

### Optional: custom hostname

Add to `/etc/hosts`: `127.0.0.1 7501-audit.local` — then open `http://7501-audit.local:5252` instead of `localhost`. Set `HOSTNAME_PRETTY=7501-audit.local` in `.env` if desired.

---

## 7. Critical behaviors and conventions

### 7.1 TXT file encoding

Inditex exports the TXT as **UTF-16-LE**, tab-delimited, 129 columns. Parsers (both JS and Python) hard-code this:

```js
new TextDecoder('utf-16le').decode(buf)
// then split on \t
```

```python
pd.read_csv(path, sep='\t', encoding='utf-16-le')
```

Other importers may use UTF-8 — add detection if you generalize.

### 7.2 Aggregation method

"Method B" = group raw TXT rows by `(ORIGIN, DESTINATION_HS, MID, invoice)` and sum quantities, weights, and invoice value. Entered-value comparison rolls Section 232 adjunct CM items into their matched parent line before diffing against TXT agg.

### 7.3 Freight & insurance allocation

Allocated pro-rata across rows by `INVOICE_VALUE` (or `AMOUNT` at the raw-line level). The user enters these as totals in the UI; the audit pro-rates them onto each line to compute entered value.

### 7.4 Chapter 99 rules

`DEFAULT_CH99_RULES` holds 77 rules covering:
- All 65 Annex I reciprocal codes (`9903.02.02`–`9903.02.71`) from EO 14326
- EU cap logic (ES, PT) — `9903.02.19` if HTSUS Col-1 MFN ≥ 15%, else `9903.02.20` at +15% (HTS table drives branch; 7501 col 33 is fallback)
- IEEPA Universal baseline (`9903.01.25`, +10%) for EG, MA
- China stack: `9903.88.15` (Section 301 List 4A +7.5%) + `9903.01.24` (IEEPA China +10%) + `9903.01.25` (IEEPA Universal +10%)
- India stack: `9903.02.26` (+25% reciprocal) + `9903.01.84` (+25% Russia-oil penalty, eff Aug 27, 2025)

Each rule carries `effective_from` and `effective_to` ISO dates. The audit selects rules based on the entry's applicable date (Entry Date first, Import Date fallback).

### 7.5 Section 301 PARTIAL status

`CH99_CHECK` has four states: MATCH, MISMATCH, MISSING, PARTIAL.

Section 301 lists are **mutually exclusive** — each Chinese HTS appears on at most one list:

| Code | List | Rate | Effective |
|---|---|---|---|
| `9903.88.01` | List 1 | +25% | Jul 6, 2018 |
| `9903.88.02` | List 2 | +25% | Aug 23, 2018 |
| `9903.88.03` | List 3 | +25% | Sep 24, 2018 |
| `9903.88.15` | List 4A | +7.5% | Sep 1, 2019 |

The engine cannot determine HTS-level list membership, so it uses a **fuzzy marker**: any `9903.88.*` code filed by the broker satisfies Section 301 coverage — a broker filing `9903.88.03` (List 3) instead of `9903.88.15` (List 4A) is **not** a mismatch.

**PARTIAL** fires only when the engine expects a Section 301 layer for a China-origin item but the broker filed **no** `9903.88.*` code at all. It surfaces as an Info advisory so the user can verify against USTR's annex whether the HTS is actually exempt from all Section 301 lists.

### 7.6 Findings rollup cap

Each finding category caps at 10 individual cards + 1 summary rollup. Categories:
- **MID consistency** (High) — TXT MID vs 7501 MID differ on matched lines
- **Chapter 99 application** (Critical for MISMATCH/MISSING on matched rows, Info for PARTIAL)
- **Reconciliation** (Critical) — agg or filed has no counterpart
- **Entered value** (Medium/High) — value diff > $5 absolute or > 0.5% relative
- **7501 extract integrity** (High/Medium) — duplicate primary rows from compound-rate splits

### 7.7 Snapshot raw-data budget

In localStorage mode, snapshots have a 500 KB cap on the raw lines array. If exceeded, raw gets dropped and `rawDropped: true` is set so the Raw Lines tab can show an explanatory empty state. Postgres mode has no cap.

---

## 8. Common extensions

If Cursor or a developer is asked to extend this tool, the most likely tasks:

### 8.1 Add a new country rule

In `DEFAULT_CH99_RULES`, add an `annexI(...)` entry:

```js
annexI("XX", "9903.02.NN", RATE, "Country Name"),
```

Then verify `expectedChapter99()` looks it up correctly. The rule will inherit the EO 14326 effective window (Aug 7, 2025 → Feb 24, 2026).

For special stacks (multi-layer like India's), add separate rule objects with explicit `effective_from`/`effective_to` and the right `category` (one of: `Reciprocal`, `Reciprocal-EU`, `IEEPA-Universal`, `IEEPA-China`, `IEEPA-India`, `Section-301`).

### 8.2 Add a new finding category

In `buildFindings(cmp, ctx)`:
1. Add a filter step to find the offending rows
2. Push card objects with shape `{sev, cat, loc, desc, rec}`
3. Add a rollup if the count exceeds `CAP` (currently 10)
4. Update the KPI tile color thresholds in `renderKpis()` if needed

### 8.3 Support a different importer's TXT format

Currently `parseInditexTxt(buf)` hard-codes:
- UTF-16-LE encoding
- Tab delimiter
- 129 columns
- Column positions for CUSTOMS_SKU (66), SKU_SALES_UNIT (68), etc.

To support another importer: split off `parseInditexTxt` into `parsers[importer]`, add format detection at upload time, and let the user pick.

### 8.4 Multi-tenant Postgres

The server currently uses one fixed database (`inditex_audit`). For SaaS, add a `tenant_id` column to `audit_runs`, key all queries on it, and add auth (Flask-Login or similar).

### 8.5 Convert to a Skill

Package the workflow as `/mnt/skills/user/inditex-audit/SKILL.md` with the dashboard's audit logic as a reusable agent capability. Skill would receive a TXT + XLSX, run the audit, and return findings JSON.

---

## 9. Testing

There's no test framework in-tree, but the dashboard ships with an inline validation suite that runs end-to-end against the Zara fixture (entry 113-3957214-9). To regenerate:

```bash
node tests/full_validation.js
```

Expected output:

```
✓ TXT rows parsed — got 389
✓ Aggregated lines — got 44
✓ Filed line items — got 44
✓ Strict matches
✓ Loose matches
✓ CH99 matches
✓ MID mismatches
✓ Findings — got 8
✓ Active run set
ALL VALIDATIONS PASSED
```

Validation reference numbers:
- Zara entry: 44 agg lines, 39 strict + 5 loose matches, 44/44 Ch99 match, Block 37 = $2,503.42 exact
- Big entry 31380: 282 agg lines, all 9 covered single-COO categories match 100% (TR 6/6, IN 1/1, TN 1/1, BD 62/62, KH 8/8, MA 14/14, PK 13/13, PT 9/9, EG 4/4). CN 39/46 (7 Section 301 PARTIAL → Info). MULTI 0/118 (known limitation — multi-COO items have no single-rule lookup)

---

## 10. Known limitations & deferred work

- **MULTI-country items** — when COO is "MULTI" the engine can't pick a country-specific rule. Currently 0/118 match on the big entry. Two options: (a) flag as warning and don't apply Ch99 expectations, or (b) expand multi-origin into per-component rules from the TXT children.
- **HTS-specific Section 301** — engine treats all CN apparel as List 4A; broker classifies HTS-by-HTS against USTR's annex. PARTIAL status mitigates false positives but doesn't fix the model. Would need a real `hts_prefix` field on each rule.
- **Section 232 splits** — steel/aluminum derivative Ch99 layers (`9903.81.*`, `9903.85.*`, `9903.01.33` exclusion) are filed on the 7501 but not in the TXT. The engine accepts these as adjunct layers on matched items (Info finding); it does not verify steel content KG or 232 rate correctness.
- **Section 232 splits** — steel/aluminum derivative Ch99 layers (`9903.81.*`, `9903.85.*`, `9903.01.33` exclusion) are filed on the 7501 but not in the TXT. The engine accepts these as adjunct layers on matched items (Info finding); it does not verify steel content KG or 232 rate correctness.
- **Compound rates** — when an HTS has a compound rate like "41c/KG + 16.3%", the 7501 export sometimes splits it into two rows. Dashboard uses the FIRST row only and flags the dupe; an alternative is summing AVD across both rows.
- **Multi-invoice TXT files** — currently assumes one invoice per TXT. Would need invoice-level scoping if Inditex changes export format.
- **Cotton fee table** — `cottonFeePerKg(hts)` covers the common cotton HTS but isn't exhaustive. Add codes as needed.

---

## 11. Source-of-truth files for Cursor

If rebuilding from scratch, in order of dependency:

1. `inditex_audit_dashboard.html` — audit engine + UI (SheetJS CDN for XLSX)
2. `inditex_audit_server.py` — Postgres persistence, auth, reference config, activity log
3. `USER_MANUAL.md` — user-facing behavior contract

No frontend build step. Docker/EB packaging lives under `Dockerfile`, `deploy.sh`, and kn-playground `applications/inditex-audit-main/`.
