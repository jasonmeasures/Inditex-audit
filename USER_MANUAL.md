# 7501 Audit — User Manual

**Version:** June 2026  
**Audience:** Customs analysts, brokers, and admins using the 7501 Audit dashboard

This guide covers day-to-day use of the web dashboard. For installation, see [SETUP.md](SETUP.md). For engineering details, see [BUILD.md](BUILD.md).

---

## 1. What this tool does

7501 Audit reconciles **Inditex source TXT** files against a **broker 7501 extract (XLSX)**. It:

- Parses importer line data and the filed entry summary
- Computes expected duty (MFN, Chapter 99 layers, cotton fee, MPF)
- Matches aggregated TXT lines to filed 7501 items
- Surfaces discrepancies as severity-ranked **findings**

The audit runs in your browser. With the Flask server connected, saved runs persist in **PostgreSQL** so your team can share history, analytics, and reference data.

---

## 2. Before you start

1. Start the app (see [SETUP.md](SETUP.md)): `./start.sh` or `python inditex_audit_server.py`
2. Open **http://localhost:5252** in your browser (do not open the `.html` file directly from Finder)
3. **Sign in** when prompted — Dashboard, Reference, Users, and Activity require authentication

### Roles

| Role | Can do |
|------|--------|
| **Collaborator** | Run audits, save/load runs, view Dashboard analytics, browse Reference (read-only) |
| **Admin** | Everything above, plus: upload HTS table, edit Chapter 99 rules, manage users, view Activity log, **Re-run all saved audits** |

Your administrator creates accounts under **Users** (admin only). On first install, an initial admin is seeded when `INITIAL_ADMIN_PASSWORD` is set in the server environment.

---

## 3. Navigation

The top bar is your home base:

| Control | Purpose |
|---------|---------|
| **Dashboard** | Browse all saved runs, portfolio analytics, import/export, bulk delete |
| **Reference** | Global HTS Classification Table, Chapter 99 rules, sources & verification (sign-in required) |
| **Users** | Create/delete users, reset passwords (admin only) |
| **Activity** | Audit trail of sign-ins and actions (admin only) |
| **+ New Run** | Clear the current audit view and start fresh (does not delete saved runs) |
| **Sign out** | End your session |

The main **Audit** view is where you upload files and review results. There is **no Saved Runs tab on the audit page** — use **Dashboard** to open prior runs.

---

## 4. Running a new audit

### 4.1 Inputs panel

The **Inputs** panel is collapsible. Click **Hide ▲** / **Show ▼** to tuck it away after a run so you can focus on results.

| Field | What to provide |
|-------|-----------------|
| **Inditex source TXT** | One or more `.txt` files (UTF-16-LE, tab-delimited). Multiple invoices in one audit are supported — add files with the file zone or remove individual files from the list. |
| **7501 extract (XLSX)** | Broker export; must include **Sheet0** |
| **Freight / Insurance** | Total USD amounts; allocated pro-rata across lines by invoice value |
| **Run Audit** | Enabled when at least one TXT and the XLSX are loaded |

### 4.2 HTS reference strip

When an HTS Classification Table is loaded (under **Reference**), a status strip appears above Inputs showing when it was last updated. Click **Open Reference** to browse codes.

### 4.3 Source file mismatch warning

If invoice numbers in the TXT and 7501 do not appear to match the same shipment, a red banner appears at the top of results. The tool uses **fuzzy invoice matching** (e.g. `001/04-29640` in the 7501 vs `29640` in the TXT).

**The audit still runs.** Review Comparison and Findings for line-level issues. If files are truly from different shipments, upload matching TXT and 7501 and run again.

### 4.4 After the run

Results show:

1. **Snapshot** — KPI cards (lines, match rate, entered value, Block 37 duty, findings, etc.)
2. **Reconciliation status** — strict/loose/no-match summary
3. **Review tabs** — detailed grids (see §5)

The Inputs panel auto-collapses after a successful run.

---

## 5. Review tabs

All review grids support **column filters** and a per-tab **↓ CSV** button (exports the current filtered view).

Use **Export all (ZIP)** above the tabs to download every review grid as separate CSV files in one ZIP.

| Tab | What you see |
|-----|----------------|
| **Comparison** | One row per aggregated line (or unmatched filed item); MATCH / MID / Ch99 status. Filter includes **232 split (adjunct)** for orphan Section 232 CM items paired to a parent. |
| **Ch99 Stack** | Expected tariff layers per line by category; filed Section 232 / 232 exclusion columns when present |
| **Raw Lines** | Individual TXT rows with computed duty |
| **Aggregated** | Method B groups (COO + HTS + MID) — the grain the 7501 files at |
| **7501 Filed** | What the broker filed, one row per item |
| **Findings** | Severity-ranked issues (Critical → Info) with recommendations |
| **Manufacturer** | MID rollup across the current entry |
| **HTS Consistency** | Within-entry HTS checks and rules baseline. **Cross-run HTS discrepancies** are on the **Dashboard**, not here |

### Comparison filters (common)

| Filter | Use when |
|--------|----------|
| **MATCH** | Strict / loose / no-match / 232 split |
| **CH99 status** | MATCH, MISMATCH, MISSING, PARTIAL |
| **Ch99 Stack → Section 232** | Review broker-filed steel/aluminum derivative layers |

---

## 6. Saving a run

After an audit completes:

1. Optionally type a name in **Name this run**
2. Click **Save run**

Saved runs appear on the **Dashboard**. The compact save bar includes a link to open Dashboard directly.

Saved snapshots store aggregation and 7501 data. **Original TXT/XLSX file bytes are not kept** in the database — only filenames and metadata. You can still re-run using stored aggregates (see §8).

---

## 7. Dashboard — saved runs & analytics

Open **Dashboard** from the top bar.

### 7.1 Portfolio overview

Scroll through summary cards: total duty, match rates, findings breakdown, importer/COO/MID analytics, MFN consistency panels, and more.

### 7.2 By Importer

The **By Importer** table rolls up saved runs by **CS Importer ID (EIN)** when present on the 7501 extract. Importer names are normalized (trimmed, collapsed whitespace) so variants like `ZARA USA INC` and `ZARA USA INC ` group together. The **EIN** column shows the identifier from the filed entry.

### 7.3 Runs list

| Action | How |
|--------|-----|
| **Load a run** | Click the run **row** (not just the expand arrow) — opens the audit view with that entry’s data |
| **Expand details** | Click **▼** on the row for metadata without loading |
| **Rename** | **Rename** button on the row |
| **Delete one** | **Delete** on the row |
| **Delete many** | Check rows → selection bar appears → **Delete selected** |
| **Search / filter** | Search box and filter chips (All / Clean / Critical / **EU cap affected**, etc.) |

Runs with ES/PT/BG lines on `9903.02.19` or `9903.02.20` show an **EU cap** badge. Use the **EU cap affected** filter to build a re-run checklist after logic or rules updates.

Pagination appears only when there are more than 25 runs.

### 7.4 Import / export / clear

| Button | Purpose |
|--------|---------|
| **Import** | Restore runs from a previously exported `.json` file |
| **Export all** | Download all saved runs as JSON (backup or migration) |
| **Clear all** | Delete every saved run (confirmation required) |

---

## 8. Update & re-run (saved runs)

When you load a saved run from Dashboard, an **Update & re-run** panel appears inside Inputs (expand Inputs if collapsed).

You can:

- Change **freight** or **insurance** — totals, comparison, findings, and KPIs refresh on re-run
- Optionally **replace TXT** or **7501** files (upload new files; otherwise stored data is reused)
- Click **Re-run audit** to recompute without deleting the saved run

The panel shows **Original source files** (filenames from when the run was saved). Labels like “Keep current TXT set” mean the audit uses data already in the saved snapshot, not files on disk.

**Re-run all saved audits** (admin, Reference tab) recomputes every stored run from its saved agg/filed snapshot — use after Chapter 99 rule or engine logic changes. It does **not** re-parse original XLSX/TXT files.

---

## 9. Reference data

Open **Reference** from the top bar (sign-in required).

Reference data is **global** — shared across all audits and all users.

### 9.1 HTS Classification Table (admin upload)

Admins upload an `.xlsx` HTS table. MFN rates from this table:

- Drive **duty projection** and HTS verification baselines
- Are shown alongside broker-filed rates in Comparison (divergences marked with a **tbl:** badge)

**EU cap branching** (`9903.02.19` vs `9903.02.20` for ES/PT/BG) uses the **broker-filed 7501 column 33 rate first** when present, then falls back to the HTS table. CBP ties the branch to the filed Column 1 / ad valorem equivalent rate on the entry.

Collaborators can **search and browse** loaded codes but cannot upload.

### 9.2 Chapter 99 rules (admin edit)

Admins edit the rules grid, **Save rules**, or **Reset to defaults**. Rules include effective date windows per executive order. EU reciprocal rules for ES/PT/BG are auto-selected by MFN branch (`eu_cap_when`).

After changing reference data or after an engine deploy, use **Re-run all saved audits** (admin, bottom of Reference) so historical runs reflect the new rules and logic.

### 9.3 Sources & verification

Read-only cards explaining tariff authority, **EU cap logic** (why `.19` vs `.20`), **Section 232 split** handling, China stack layers, and data provenance.

---

## 10. Tariff logic — what analysts should know

### 10.1 EU cap (ES, PT, BG)

For EU origin goods, reciprocal duty is capped at a **15% landed rate**:

| Filed Column 1 rate (col 33) | Expected Ch99 | Reciprocal duty |
|------------------------------|---------------|-----------------|
| **≥ 15%** | `9903.02.19` | 0% additional (full Col-1 on primary line) |
| **&lt; 15%** (incl. Free) | `9903.02.20` | +15% additive (CBP: duty on Ch99 line, $0 on primary) |

The engine flags **EU cap branch mismatch** when the broker filed the wrong `.19`/`.20` for the Col-1 rate. A common pattern: primary at exactly 15% with `9903.02.20` filed at FREE — wrong **heading**, but duty placement may still match the `.19` economic outcome. Review the 7501 Filed tab and consider a PSC to correct the Ch99 code.

### 10.2 Section 232 (steel / aluminum derivatives)

Products with reportable steel or aluminum content may file extra Ch99 rows on the **same CM item** that are not in the importer TXT, for example:

- `9903.01.33` — reciprocal exclusion when 232 applies
- `9903.81.91` — steel derivative duty

The engine **accepts** these as adjunct layers:

- **Ch99 MATCH** on the primary line (reciprocal expectation waived when a 232 stack is filed)
- **Info** finding: *Section 232 stack* — not Critical

If the ACE extract puts `9903.81.*` on a **separate CM item**, the engine pairs it to the nearest matched parent as **232 SPLIT (7501 adjunct)**.

The tool does **not** verify steel content KG or 232 rate correctness — confirm against the broker’s steel declaration manually.

### 10.3 Section 301 (China)

Expected layers include a fuzzy Section 301 marker when list membership cannot be determined at HTS level. **PARTIAL** in Comparison means the broker filed no `9903.88.*` code — confirm against USTR annexes.

---

## 11. Admin: Users & Activity

### Users (admin)

- **+ New user** — set username, password, role (Collaborator or Admin)
- **Change password** / **Delete** per user

### Activity (admin)

Filter by user or action type (login, run_audit, save_run, load_run, upload_hts_table, etc.). Use **Refresh** to pull the latest log.

---

## 12. Tips & conventions

### Matching logic

- **Strict match:** same COO + HTS + MID on TXT and 7501
- **Loose match:** same COO + HTS, MID differs (often OCR/fill-down defects on the extract)
- **No match:** row exists on one side only
- **232 SPLIT (7501 adjunct):** Section 232 Ch99 on its own CM item, paired to a matched parent

### Findings severity

| Severity | Typical categories |
|----------|-------------------|
| **Critical** | Chapter 99 application (wrong/missing reciprocal layer), reconciliation gaps |
| **High** | MID consistency, entered value drift |
| **Info** | Section 232 stack, Section 301 coverage advisory (PARTIAL) |

### Storage indicator

When connected to Postgres via the server, runs persist in the database with no browser quota. If you open the HTML offline, the app may fall back to browser storage (limited) — always use `http://localhost:5252` for production use.

### Keyboard / UX

- **+ New Run** clears the current audit display but does not delete saved runs
- Hard-refresh the browser after a server deploy to pick up UI updates (`Cmd+Shift+R` on Mac)

---

## 13. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Stuck on sign-in screen | Check username/password; confirm server is running and `/api/health` responds |
| Loaded run shows wrong data | Ensure you clicked the **row** on Dashboard to load; hard-refresh if needed |
| “Storage: browser localStorage” | You opened `file://` — use `http://localhost:5252` |
| Re-run didn’t change totals | Expand Inputs, confirm freight/insurance in **Update & re-run**, click **Re-run audit** |
| Old runs still show wrong EU cap | Reference → **Re-run all saved audits** (admin), or re-upload 7501 and re-run per entry |
| EU cap mismatch at exactly 15% | Engine expects `9903.02.19` per CBP (Col-1 ≥ 15%); broker may have used `.20` with FREE — check duty placement |
| CSV export button disabled | Run an audit first (or load a saved run) |
| Reference locked | Sign in; collaborators have read-only access |
| HTS table missing | Ask an admin to upload under **Reference** |
| Importer EIN blank on Dashboard | Re-upload 7501 extract (EIN backfilled from snapshot on save) or re-run after deploy |
| Server won’t start | See [SETUP.md](SETUP.md) — Postgres running, port free, venv deps installed |

---

## 14. Getting help

- **Setup / install issues:** [SETUP.md](SETUP.md)
- **How the engine works:** [BUILD.md](BUILD.md)
- **Playground / production URL:** ask your KlearNow admin — deploys ship via kn-playground merge + Inditex Audit Deploy workflow
