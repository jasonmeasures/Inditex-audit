# 7501 Audit — User Manual

**Version:** June 2026 (Dashboard landing, review sign-off, rate-determination date)  
**Audience:** Customs analysts, brokers, and admins using the 7501 Audit dashboard

This guide covers day-to-day use of the web dashboard. For installation, see [SETUP.md](SETUP.md). For engineering details, see [BUILD.md](BUILD.md).

---

## 1. What this tool does

7501 Audit reconciles **Inditex source TXT** files against a **broker 7501 extract (XLSX)**. It:

- Parses importer line data and the filed entry summary
- Computes expected duty (MFN, Chapter 99 layers, cotton fee, MPF)
- Matches aggregated TXT lines to filed 7501 items
- Surfaces discrepancies as severity-ranked **findings**
- Tracks **reviewer sign-off** per saved run

The audit runs in your browser. With the Flask server connected, saved runs persist in **PostgreSQL** so your team can share history, analytics, and reference data.

---

## 2. Before you start

1. Start the app (see [SETUP.md](SETUP.md)): `./start.sh` or `python inditex_audit_server.py`
2. Open **http://localhost:5252** in your browser (do not open the `.html` file directly from Finder)
3. **Sign in** when prompted — you land on the **Dashboard** automatically

### Roles

| Role | Can do |
|------|--------|
| **Collaborator** | Run audits, save/load runs, view Dashboard analytics, sign off reviews, browse Reference (read-only) |
| **Admin** | Everything above, plus: upload HTS table, edit Chapter 99 rules, import/export/clear runs, manage users, view Activity log, **Re-run all saved audits** |

Your administrator creates accounts under **Users** (admin only). On first install, an initial admin is seeded when `INITIAL_ADMIN_PASSWORD` is set in the server environment.

---

## 3. Navigation

The top bar is your home base:

| Control | Purpose |
|---------|---------|
| **Dashboard** | Default home — portfolio analytics and saved runs (always returns here; does not toggle off) |
| **Reference** | HTS table, Chapter 99 rules, Recent Activity, run data tools (admin), sources & verification |
| **Users** | Create/delete users, reset passwords (admin only) |
| **Activity** | Full audit trail (admin only) |
| **+ New Run** | Open the audit upload view for a new entry |
| **Sign out** | End your session |

The **Audit** view (upload, tabs, findings) opens when you click **+ New Run** or load a run from the Dashboard. There is **no Saved Runs tab on the audit page**.

---

## 4. Running a new audit

Click **+ New Run** from the top bar.

### 4.1 Inputs panel

The **Inputs** panel is collapsible. Click **Hide ▲** / **Show ▼** to tuck it away after a run.

| Field | What to provide |
|-------|-----------------|
| **Inditex source TXT** | One or more `.txt` files (UTF-16-LE, tab-delimited). Multiple invoices supported. |
| **7501 extract (XLSX)** | Broker export; must include **Sheet0** |
| **Freight / Insurance** | Total USD amounts; allocated pro-rata across lines by invoice value |
| **Run Audit** | Enabled when at least one TXT and the XLSX are loaded |

### 4.2 HTS reference strip

When an HTS Classification Table is loaded (under **Reference**), a status strip appears above Inputs. Click **Open Reference** to browse codes.

### 4.3 Source file mismatch warning

If invoice numbers in the TXT and 7501 do not match the same shipment, a red banner appears. The tool uses **fuzzy invoice matching** (e.g. `001/04-29640` ↔ `29640`). **The audit still runs.**

### 4.4 After the run

Results show Snapshot KPIs, Reconciliation status, and Review tabs (see §5). The Inputs panel auto-collapses. The run is saved to the database when connected to Postgres.

---

## 5. Review tabs

All review grids support **column filters** and per-tab **↓ CSV**. Use **Export all (ZIP)** for every grid in one download.

| Tab | What you see |
|-----|----------------|
| **Comparison** | MATCH / MID / Ch99 status per line; filter **232 split (adjunct)** |
| **Ch99 Stack** | Expected layers by category; filed Section 232 columns |
| **Raw Lines** | Individual TXT rows with computed duty |
| **Aggregated** | Method B groups (COO + HTS + MID) |
| **7501 Filed** | Broker-filed items |
| **Findings** | Critical → Info with recommendations |
| **Manufacturer** | MID rollup |
| **HTS Consistency** | Within-entry checks; cross-run HTS discrepancies are on **Dashboard** |

### Comparison filters (common)

| Filter | Use when |
|--------|----------|
| **MATCH** | Strict / loose / no-match / 232 split |
| **CH99 status** | MATCH, MISMATCH, MISSING, PARTIAL, **REVIEW** |
| **Ch99 Stack → Section 232** | Steel/aluminum derivative layers |

---

## 6. Saving a run

After an audit completes, optionally name the run and click **Save run**. Saved runs appear on the **Dashboard**. Original TXT/XLSX bytes are not stored — only filenames and computed snapshots.

---

## 7. Dashboard — saved runs & analytics

Opens automatically after sign-in and refresh. Click **Dashboard** anytime to return from the audit view.

### 7.1 Portfolio overview

Summary cards: total duty, match rates, findings breakdown, importer/COO/MID analytics, MFN consistency panels, and more.

### 7.2 By Importer

Rollup by **CS Importer ID (EIN)** when present on the 7501. Names are normalized so variants group together. A **Totals** row and footer summarize all importers in view.

### 7.3 Runs list

| Column / action | Purpose |
|-----------------|---------|
| **Issues** | Compact preview of top findings (critical/high counts) |
| **Review** | Current sign-off status |
| **▼ Expand** | Full issues list, review form, **Open full audit** |
| **Click row** | Load the complete audit view |
| **Rename / Delete** | Per-run actions |
| **Bulk delete** | Check rows → **Delete selected** |
| **Search / filter** | Text search; status chips; **All reviews** dropdown; **EU cap affected** |

Review statuses: **Not reviewed**, **In progress**, **Reviewed**, **Needs deeper review**, **Broker contacted**, **Data issue**, **Waived**.

Pagination appears when there are more than 25 runs.

### 7.4 Review sign-off (Dashboard expand row)

From the expanded row you can:

1. Set **Review status** and optional **note**
2. Click **Save review** — persists to the database and syncs to the audit view when you open that run

The same controls appear in the **review bar** at the top of the audit view for a loaded run.

---

## 8. Update & re-run (saved runs)

Load a run from Dashboard. Expand **Inputs** if collapsed to see **Update & re-run**:

- Change **freight** or **insurance**
- Optionally replace TXT or 7501
- Click **Re-run audit**

**Re-run all saved audits** (admin, Reference tab) recomputes every stored run from saved agg/filed data after rule or engine changes. It does not re-parse original files.

---

## 9. Reference data

Open **Reference** from the top bar (sign-in required). Reference data is **global** — shared across all users.

### 9.1 HTS Classification Table (admin upload)

Admins upload an `.xlsx` HTS table. MFN rates drive duty projection and HTS verification. **EU cap branching** still uses **7501 column 33 first**, then the HTS table as fallback.

### 9.2 Chapter 99 rules (admin edit)

Admins edit the rules grid, **Save rules**, or **Reset to defaults**. EU reciprocal rules for ES/PT/BG are auto-selected by MFN branch (`eu_cap_when`).

### 9.3 Recent Activity

Sign-in events, audits run, saves, loads, and reference changes — moved here from the Dashboard for a cleaner portfolio view.

### 9.4 Run data management (admin only)

| Button | Purpose |
|--------|---------|
| **Import** | Restore runs from a previously exported `.json` file |
| **Export all** | Download all saved runs as JSON (backup or migration) |
| **Clear all** | Delete every saved run (confirmation required) |

### 9.5 Sources & verification

Read-only cards: tariff authority, **EU cap logic**, **Section 232**, China stack, data provenance.

### 9.6 Re-run all saved audits (admin)

Bottom of Reference — recomputes comparison/findings for every saved run using current rules and engine logic.

---

## 10. Tariff logic — what analysts should know

### 10.1 Rate-determination date

Chapter 99 expectations use a **rate-determination date**, not raw entry date alone. Resolved from the 7501 extract in priority order:

1. **IT Date** (Block 17) — immediate transportation at port of original importation
2. **Warehouse withdrawal date** — entry type 31
3. **Latest release date** (Block 7) — default time of entry
4. Fallbacks: entry date → import date (Block 11)

The Snapshot KPI **Ch99 rules as of** shows this date and its source (IT / release / etc.). Tariff effective windows are tested against this date.

### 10.2 EU cap (ES, PT, BG)

Authority: EO 14326, CBP CSMS #65829726. For EU origin, reciprocal duty is capped at **15% landed**:

| Filed Column 1 rate (col 33) | Expected Ch99 | Reciprocal duty |
|------------------------------|---------------|-----------------|
| **≥ 15%** | `9903.02.19` | 0% additional |
| **&lt; 15%** (incl. Free) | `9903.02.20` | +15% additive on Ch99 line |

Example: perfume `3303.00.3000` with Col-1 **Free** → expect **`9903.02.20`** (broker was correct if they filed `.20`).

**Effective-date guards** (by rate-determination date):

| Window | Behavior |
|--------|----------|
| Before **2025-08-07** (or in-transit grandfather) | Prior **10%** regime (`9903.01.25`), not 9903.02.x |
| **2025-08-07** → **2026-02-19** | Truth table above |
| **2026-02-20** onward | **REVIEW** — `NEEDS_REVIEW_EO14389`; human review required (EO 14389; USITC has not updated HTS) |

**EU cap branch mismatch** flags wrong `.19`/`.20` for the Col-1 rate. At exactly 15% with `.20` filed, the heading may be wrong but duty placement can still match economically — review 7501 Filed and consider a PSC.

### 10.3 Section 232 (steel / aluminum)

Extra Ch99 rows on the same CM item (`9903.01.33` + `9903.81.*`) are accepted as **Info**, not Critical. Separate CM-item 232 lines pair as **232 SPLIT (7501 adjunct)**.

### 10.4 Section 301 (China)

**PARTIAL** means no `9903.88.*` filed — confirm against USTR annexes.

---

## 11. Admin: Users & Activity

### Users (admin)

Create users, change passwords, delete accounts.

### Activity (admin)

Full filterable log under **Activity** in the top bar. Summary feed also under **Reference → Recent Activity**.

---

## 12. Tips & conventions

### Matching logic

- **Strict:** COO + HTS + MID match
- **Loose:** COO + HTS match, MID differs
- **No match:** one side only
- **232 SPLIT:** orphan 232 CM item paired to parent

### Findings severity

| Severity | Typical categories |
|----------|-------------------|
| **Critical** | Chapter 99 application (wrong/missing layer) |
| **High** | MID consistency, entered value drift |
| **Info** | Section 232 stack, Section 301 advisory, **EO 14389 review** |

### Storage

Use `http://localhost:5252` with the Flask server for Postgres persistence. Opening the HTML file directly falls back to limited browser storage.

### After a deploy

Hard-refresh (`Cmd+Shift+R` on Mac) to load the latest UI.

---

## 13. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Lands on audit page instead of Dashboard | Hard-refresh; confirm you are signed in |
| Dashboard empty / loading forever | Hard-refresh; check `/api/health`; HTS download runs in background after dashboard opens |
| Stuck on sign-in | Check credentials; confirm server is running |
| Loaded run shows wrong data | Click the **row** on Dashboard, not just expand |
| Re-run didn’t change totals | Expand Inputs → **Update & re-run** → change freight/insurance |
| Old EU cap verdicts | Reference → **Re-run all saved audits** (admin) |
| EU cap at exactly 15% with `.20` filed | Heading mismatch possible; check duty dollars on Ch99 vs primary line |
| Import / Export / Clear missing | Admin only — **Reference → Run data management** |
| Review status not saving | Confirm Postgres backend; check network tab for `PATCH /api/runs/.../review` |
| Reference locked | Sign in |
| Server won’t start | See [SETUP.md](SETUP.md) |

---

## 14. Getting help

- **Setup:** [SETUP.md](SETUP.md)
- **Engine / API:** [BUILD.md](BUILD.md)
- **EU reciprocal regression tests:** `python3 verify_eu_reciprocal_rules.py`
- **Playground / production:** kn-playground merge → Inditex Audit Deploy workflow
