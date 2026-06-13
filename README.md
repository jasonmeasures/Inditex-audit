# 7501 Audit

A local-first reconciliation tool for US Customs Form 7501 filings. Given an importer's commercial source data and the filed 7501 extract, it computes the expected duty stack (MFN + Chapter 99 layers + cotton fee + MPF), compares it to what was filed, and surfaces every gap as a triaged finding.

Built and validated against an Inditex / Zara entry (113-3957214-9, Jan 2026) that reconciled 44 of 44 lines and matched the filed Block 37 duty of **$2,503.42** to the penny.

---

## Quick start

```bash
# 1. Install Python deps
pip install flask psycopg2-binary

# 2. (Optional) Add a friendly hostname  → http://7501-audit.local
./setup-hostname.sh

# 3. Start Postgres locally if it isn't already
brew services start postgresql      # macOS
sudo service postgresql start       # Linux

# 4. Run the server (auto-creates DB and schema on first run)
python inditex_audit_server.py
```

Open **http://7501-audit.local:5252** (or `http://localhost:5252` if you skipped step 2).

Run on port 80 for a cleaner URL:
```bash
sudo PORT=80 python inditex_audit_server.py     # then  →  http://7501-audit.local
```

---

## What it does

Three input modes — the same logic runs end-to-end in any of them:

1. **HTML dashboard** (`inditex_audit_dashboard.html`) — drop in a TXT + 7501 extract, hit Run Audit. Tabs for Comparison, Chapter 99 Stack, Raw Lines, Aggregated, 7501 Filed, Findings, Rules, Sources & Verification.
2. **Python CLI** (`inditex_audit.py`) — `python inditex_audit.py --txt FILE --xlsx FILE --freight USD --insurance USD --output AUDIT.xlsx`. Produces an 8-sheet workbook with the same reconciliation.
3. **Flask + Postgres** (`inditex_audit_server.py`) — serves the dashboard and persists every saved run as JSONB plus denormalized metadata columns for SQL queries across entries.

The audit pipeline (same in all three):

1. Parse the importer source (Inditex CUSTOMS TXT, UTF-16-LE, 129 columns) into 389 line items.
2. Allocate freight + insurance across lines pro-rata on invoice value.
3. Aggregate to the (COO, HTS, MID) grain using Method B — this is the unit the 7501 actually files at.
4. Look up the expected Chapter 99 stack per (COO, HTS, entry date) against a versioned rules table. Reciprocal, IEEPA Universal, IEEPA China/HK, and Section 301 each get their own layer.
5. Compute expected MFN duty, Ch99 duty per layer, cotton fee, MPF.
6. Match each aggregated line to a filed 7501 item — strict first (exact COO+HTS+MID), loose fallback (MID similarity catches the OCR defect on the 7501 extract where MIDs get filled-down across items 12–16).
7. Diff expected vs filed for every monetary field. Surface every gap as a finding with severity.

## What it caught

Validated against the Zara Jan 2026 entry:

- **44/44 aggregated lines** mapped to 44/44 filed items.
- **39 strict matches + 5 loose matches** — the 5 loose were the OCR defect (the 7501 extract had bogus MID `PKCOMKN145LAH` filled down across items 12–16; the audit correctly identified the true MIDs from the TXT).
- **44/44 Chapter 99 layers correct** — total Ch99 duty $1,274.53 computed vs $1,274.56 filed (within $0.03 rounding).
- **8 findings raised** — 5 High-severity MID consistency issues (the OCR defect) plus 3 finds on duplicate-HTS rows in the 7501 extract where compound-rate lines (e.g. `41¢/kg + 16.3%`) got split into two rows with the same AVD copied to both.
- **Block 37 duty $2,503.42 = $2,503.42** to the cent.

---

## Files in this repo

| File | Purpose |
|---|---|
| `inditex_audit_dashboard.html` | Single-file dashboard — opens in any browser, KlearNow-branded UI |
| `inditex_audit_server.py` | Flask + Postgres backend, serves the dashboard + REST API |
| `inditex_audit.py` | Stand-alone Python CLI producing an Excel audit workbook |
| `setup-hostname.sh` | One-time helper that maps `7501-audit.local` → `127.0.0.1` in `/etc/hosts` |
| `ARCHITECTURE.md` | Deep dive on the audit logic, rules engine, data flow — for engineers |
| `README.md` | This file |

---

## URL masking — `7501-audit.local`

The setup script adds one line to `/etc/hosts`:

```
127.0.0.1   7501-audit.local
```

This is purely a local alias — no DNS, no network exposure, the dashboard still binds only to your machine. Address bar reads `http://7501-audit.local` instead of `localhost`. The Saved Runs status indicator says `Storage: Database · connected` instead of `Storage: PostgreSQL · inditex_audit@localhost:5432`. Nothing about the underlying service is visible to anyone looking over your shoulder.

Remove the alias any time:
```bash
sudo sed -i '' '/7501-audit.local/d' /etc/hosts     # macOS
sudo sed -i '/7501-audit.local/d' /etc/hosts        # Linux
```

---

## Storage modes (auto-detected by the dashboard)

Three backends, picked automatically at page load:

1. **Postgres** — when the Flask server is running and `/api/health` responds, every save/rename/delete writes straight through to the database. No quota cap; full SQL access to your audit history; multi-user-safe.
2. **Browser localStorage** — when you open the HTML file directly (no server), runs persist in your browser. ~28 KB per slim snapshot, so 5 MB localStorage comfortably fits 150+ runs. Auto-prunes oldest when full.
3. **In-memory** — fallback for Chrome's `file://` localStorage block. Runs persist only for the current page session; the dashboard warns you to **Export to JSON** before reloading.

The dashboard's storage indicator at the top of the Saved Runs tab always tells you which mode you're in.

---

## REST API (Postgres mode)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | DB connectivity + run count |
| `GET` | `/api/runs` | All saved runs, full snapshots |
| `GET` | `/api/runs/_summary` | Lightweight metadata-only view |
| `GET` | `/api/runs/<id>` | One run |
| `POST` | `/api/runs` | Upsert a run (body = full snapshot) |
| `PUT` | `/api/runs/<id>` | Rename — body `{"name": "..."}` |
| `DELETE` | `/api/runs/<id>` | Remove one |
| `DELETE` | `/api/runs` | Remove all |

CORS is open so you can hit the API from notebooks, scripts, or other local tools.

Useful SQL queries against the underlying table:

```sql
-- Entries by importer
SELECT entry_num, invoice_num, saved_at, agg_lines, total_duty, findings_count
FROM audit_runs
WHERE importer ILIKE '%ZARA%'
ORDER BY saved_at DESC;

-- Entries with critical findings
SELECT name, entry_num, findings_critical, findings_high, total_duty
FROM audit_runs WHERE findings_critical > 0;

-- Total duty by month
SELECT date_trunc('month', saved_at) AS month,
       COUNT(*) AS entries,
       SUM(total_duty) AS duty_total
FROM audit_runs GROUP BY 1 ORDER BY 1;

-- Find a specific HTS across the whole history (JSONB drill-down)
SELECT id, name, entry_num
FROM audit_runs,
     jsonb_array_elements(data->'state'->'filed') AS line
WHERE line->>'HTS' LIKE '6110%';
```

---

## Environment variables

All optional, all have sensible defaults:

| Var | Default | Notes |
|---|---|---|
| `PGHOST` | `localhost` | |
| `PGPORT` | `5432` | |
| `PGUSER` | `$USER` | Your OS username |
| `PGPASSWORD` | empty | Set if your local PG requires it |
| `PGDATABASE` | `inditex_audit` | Auto-created on first run |
| `PORT` | `5252` | Flask port; set to `80` (needs sudo) for clean URL |
| `HOSTNAME_PRETTY` | `7501-audit.local` | Must match your `/etc/hosts` entry |

---

## Out of scope

- This tool is post-filing reconciliation. Pre-file validation (catching errors before submitting to ABI) is a separate workflow.
- It surfaces duty gaps but does not file CAPE / PSC refunds. That's a separate workflow tracked under CORE-69855.
- It uses the locally-validated Chapter 99 rules set as of EO 14326 (Aug 5, 2025, effective Aug 7, 2025 → Feb 24, 2026). When new EOs land, edit `DEFAULT_CH99_RULES` in the dashboard JS or the rules row in Postgres — the audit re-runs against the new rules without code changes.

See `ARCHITECTURE.md` for the deep dive on rule structure, the entity model the Postgres backend writes to, and how to extend the tool to new customer source formats (BASF PMS, Hershey XML, etc.).
