# 7501 Audit — Playground User Guide

**Version:** June 2026  
**Audience:** Customs analysts, brokers, and reviewers using the **hosted** KlearNow playground (not local install)

This guide covers day-to-day use of the shared web app. For installing the tool on your own machine, see [USER_MANUAL.md](USER_MANUAL.md) and [SETUP.md](SETUP.md).

---

## 1. What this tool does

7501 Audit reconciles **Inditex source TXT** files against a **broker 7501 extract (XLSX)**. It:

- Parses importer line data and the filed entry summary
- Computes expected duty (MFN, Chapter 99 layers, cotton fee, MPF)
- Matches aggregated TXT lines to filed 7501 items
- Surfaces discrepancies as severity-ranked **findings**
- Tracks **reviewer sign-off** per saved run

Your team shares one **database** on playground — saved runs, reference data, and analytics are visible to everyone who is signed in.

---

## 2. Getting started

### 2.1 Open the app

1. Use the **playground URL** your KlearNow administrator gave you (bookmark it).
2. Open it in **Chrome** or **Edge** (recommended). Safari works; avoid opening a downloaded `.html` file from email or Finder — that mode does not connect to the server.
3. **Sign in** with the username and password your administrator created for you.
4. After sign-in you land on the **Dashboard** automatically.

> **Wrong URL?** If you see a banner about `file://` or `localhost`, you are not on the hosted app. Ask your admin for the playground link.

### 2.2 Roles

| Role | Can do |
|------|--------|
| **Collaborator** | Run audits, save/load runs, view Dashboard analytics, sign off reviews, browse Reference (read-only) |
| **Admin** | Everything above, plus: upload HTS table, edit Chapter 99 rules, import/export/clear runs, manage users, view Activity log, **Re-run all saved audits** |

Need an account or password reset? Contact your **KlearNow admin** (Users tab is admin-only).

### 2.3 After an app update

When engineering deploys a new version, **hard-refresh** your browser so you load the latest UI:

- **Mac:** `Cmd + Shift + R`
- **Windows:** `Ctrl + Shift + R`

If you see a **“Stale UI detected”** banner at the top, hard-refresh before trusting analytics or new rule logic.

---

## 3. Navigation

The top bar is your home base:

| Control | Purpose |
|---------|---------|
| **Dashboard** | Default home — portfolio analytics and saved runs |
| **Reference** | HTS table, Chapter 99 rules, Recent Activity, run data tools (admin) |
| **Users** | Create/delete users, reset passwords (**admin only**) |
| **Activity** | Full audit trail (**admin only**) |
| **+ New Run** | Open the audit upload view for a new entry |
| **Sign out** | End your session (you will need to sign in again) |

The **Audit** view opens when you click **+ New Run** or load a run from the Dashboard. There is **no Saved Runs tab on the audit page** — use the Dashboard to open prior work.

---

## 4. Running a new audit

Click **+ New Run** from the top bar.

### 4.1 Inputs panel

The **Inputs** panel is collapsible. Click **Hide ▲** / **Show ▼** after a run to tuck it away.

| Field | What to provide |
|-------|-----------------|
| **Inditex source TXT** | One or more `.txt` files (UTF-16-LE, tab-delimited). Multiple invoices supported. |
| **7501 extract (XLSX)** | Broker export; must include **Sheet0** |
| **Freight / Insurance** | Total USD amounts; allocated pro-rata across lines by invoice value |
| **Run Audit** | Enabled when at least one TXT and the XLSX are loaded |

### 4.2 HTS reference strip

When an admin has uploaded the **HTS Classification Table** (under **Reference**), a status strip appears above Inputs. EU cap logic and duty projection use this table when it is loaded.

If the strip says no HTS table is loaded, ask an **admin** to upload it before relying on EU cap or MFN findings.

### 4.3 Source file mismatch warning

If invoice numbers in the TXT and 7501 do not match the same shipment, a red banner appears. The tool uses **fuzzy invoice matching** (e.g. `001/04-29640` ↔ `29640`). **The audit still runs.**

### 4.4 After the run

Results show Snapshot KPIs, Reconciliation status, and Review tabs (see §5). The Inputs panel auto-collapses. The run is **saved to the shared database** automatically when the audit completes.

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
| **Findings** | Critical → Info with recommendations — **start here** for what needs human judgment |
| **Manufacturer** | MID rollup |
| **HTS Consistency** | Within-entry checks; cross-run HTS discrepancies are on **Dashboard** |

The **Findings** tab is the engine’s triage list. **Reviewer sign-off** (§7.5–7.8) is your team’s workflow on top of that — it does not auto-clear findings; it records whether someone has looked at the entry and what follow-up is needed.

### Comparison filters (common)

| Filter | Use when |
|--------|----------|
| **MATCH** | Strict / loose / no-match / 232 split |
| **CH99 status** | MATCH, MISMATCH, MISSING, PARTIAL, **REVIEW** |
| **Ch99 Stack → Section 232** | Steel/aluminum derivative layers |

---

## 6. Saving a run

Completed audits are saved to the **shared playground database**. You can optionally rename a run from the Dashboard. Original TXT/XLSX bytes are **not** stored — only filenames and computed snapshots. To keep a full backup including raw data, an admin can **Export all** from Reference.

---

## 7. Dashboard — saved runs & analytics

Opens automatically after sign-in. Click **Dashboard** anytime to return from the audit view.

### 7.1 Portfolio overview

Summary cards: total duty, match rates, findings breakdown, importer/COO/MID analytics, MFN consistency panels, and more. Data reflects **all saved runs** in the shared database, not just yours.

### 7.2 By Importer

Rollup by **CS Importer ID (EIN)** when present on the 7501. Names are normalized so variants group together.

### 7.3 Runs list

| Column / action | Purpose |
|-----------------|---------|
| **Issues** | Top 1–2 findings at a glance (severity + short description), or **Clean** if none |
| **Review** | Reviewer sign-off badge (see §7.7) |
| **▼ Expand** | Issues summary, review form, entry metadata, **Open full audit** |
| **Click row** | Load the complete audit view (same run, all tabs) |
| **Rename / Delete** | Per-run actions (delete affects everyone on playground) |
| **Bulk delete** | Check rows → **Delete selected** |
| **Search / filter** | Text search; finding severity chips; **All reviews** dropdown; **EU cap affected** |

**Issues column** shows a compressed preview from the saved findings digest — enough to prioritize your queue without opening every entry. Expand the row (▼) for up to ~12 issue cards, or click **Open full audit** for the complete Findings tab and line-level Comparison.

**Review queue cards** (top of Dashboard runs section):

| Card | Meaning |
|------|---------|
| **Pending Review** | Runs still **Not reviewed** or **In progress** — click to filter the list |
| **Follow-up** | Runs marked **Needs deeper review**, **Broker contacted**, or **Data issue** |
| **EU Cap Re-run** | Entries with ES/PT/BG reciprocal lines — useful after rule/engine updates |

Use the **All reviews** dropdown to filter by a single status (e.g. only **Broker contacted**).

### 7.4 HTS Discrepancies Across Runs

Shows HTS codes filed at **different MFN rates** on different saved entries (spread **> 1%**). Small spreads (e.g. 14.9% vs 15.0%) are intentionally not flagged.

### 7.5 Two layers of “review”

| Layer | What it is | Where |
|-------|------------|--------|
| **Engine findings** | Automated Critical / High / Info issues from comparison | Audit → **Findings** tab; Dashboard **Issues** column |
| **Reviewer sign-off** | Human workflow status + notes for the team | Dashboard expand row; audit **Reviewer sign-off** bar |

Sign-off answers: *“Has a person looked at this entry, and what is the disposition?”* It does **not** change duty math or dismiss findings automatically. If you **re-run** an audit or an admin **Re-runs all saved audits**, findings may change — check sign-off still applies or update status/notes.

### 7.6 Where to record sign-off

You can sign off from **either** place (same data, visible to everyone):

**A — Dashboard (quick triage)**  
1. Find the run in the **Audit Runs** table.  
2. Click **▼ Expand** on the row (do not need to open the full audit).  
3. In **Reviewer sign-off**, pick a status, add an optional note, click **Save review**.  
4. Use **Open full audit** when you need Comparison / Findings detail.

**B — Full audit view (deep review)**  
1. Click the **row** to load the entry (or open from **+ New Run** after a fresh audit).  
2. Work through Snapshot, Comparison, Findings, etc.  
3. Use the **Reviewer sign-off** bar below the save bar.  
4. Click **Save review**.

**Important:** On a **brand-new audit** that is not saved yet, sign-off controls are disabled until the run is saved. The hint reads *“Save this run first to record reviewer sign-off.”* After **Run Audit** on playground, the run is usually saved automatically — sign-off should be available immediately on loaded saves.

After save, the bar shows **who** last updated review and **when** (e.g. `Last updated by jsmith · 6/25/2026, 2:15 PM`).

### 7.7 Review statuses — when to use each

| Status | Use when |
|--------|----------|
| **Not reviewed** | Default — no one has started, or you are resetting after a full re-run |
| **In progress** | You are actively working the entry; others should not assume it is closed |
| **Reviewed** | Findings understood; no broker action needed (or only immaterial Info items remain) |
| **Needs deeper review** | Escalate to a senior analyst, counsel, or second pair of eyes |
| **Broker contacted** | PSC / broker ticket opened; waiting on broker response |
| **Data issue** | Bad TXT, wrong 7501 extract, missing files — fix source data and re-run |
| **Waived / accepted** | Known acceptable variance documented (e.g. immaterial rounding, accepted broker practice) |

**Notes field** — free text visible to the whole team. Good examples:

- `Broker ticket #48291 — EU cap .20 on Free col-1, awaiting PSC`
- `Entered value $1.32 gap within tolerance — waived per SOP`
- `Re-run after HTS table upload 6/25 — was false .19, now clean`

Notes are optional but strongly recommended for **Broker contacted**, **Data issue**, and **Waived**.

### 7.8 Suggested review workflow

A practical sequence for customs analysts:

1. **Triage on Dashboard** — sort/filter by **Pending Review** or critical/high chips; scan **Issues** column.  
2. **Expand or open** entries with Critical Chapter 99 or High entered-value / MID findings first.  
3. **Findings tab** — read recommendations; use **Comparison** with CH99 / MATCH filters for line proof.  
4. **7501 Filed** + **Ch99 Stack** — confirm broker layers and duty dollars (especially EU cap `.19`/`.20` and Section 232 stacks).  
5. **Decide disposition** — broker action, waive, escalate, or fix data.  
6. **Save review** with status + note.  
7. **Export** — use **↓ CSV** or **Export all (ZIP)** if you need audit evidence outside the tool.

### 7.9 Findings severity vs sign-off

Engine severity guides priority; sign-off tracks your process:

| Severity | Typical meaning | Sign-off guidance |
|----------|-----------------|-------------------|
| **Critical** | Wrong/missing Chapter 99 layer on a matched line | Rarely **Reviewed** until resolved or explicitly waived with note |
| **High** | MID mismatch, entered value drift | **Reviewed** if immaterial; else **Broker contacted** or **Needs deeper review** |
| **Info** | Section 232 stack, Section 301 advisory, EO 14389 review flag | Often **Reviewed** after acknowledgment; EO 14389 may need **Needs deeper review** |

**CH99 status = REVIEW** (Info) means the rate-determination date is on/after **2026-02-20** — the tool will not auto-pick EU reciprocal expectations. Treat as a human decision, not a broker typo.

**Clean** entries (no Critical/High in Issues) can still be marked **Reviewed** to show the queue is cleared.

---

## 8. Update & re-run (saved runs)

Load a run from Dashboard. Expand **Inputs** to see **Update & re-run**:

- Change **freight** or **insurance**
- Optionally replace TXT or 7501
- Click **Re-run audit**

**Re-run all saved audits** (admin, Reference tab) recomputes every stored run after rule or engine changes. It does not re-parse original files.

---

## 9. Reference data (shared)

Open **Reference** from the top bar. Data here is **global** — one HTS table and one rules set for all users.

### 9.1 HTS Classification Table (admin upload)

Admins upload the team’s `.xlsx` HTS table. MFN rates drive duty projection and **EU cap branching** (`9903.02.19` vs `9903.02.20`) from true HTSUS Column 1 rates.

### 9.2 Chapter 99 rules (admin edit)

Admins edit the rules grid and **Save rules**. Collaborators can read but not edit.

### 9.3 Recent Activity

Sign-ins, audits run, saves, loads, and reference changes.

### 9.4 Run data management (admin only)

| Button | Purpose |
|--------|---------|
| **Import** | Restore runs from a previously exported `.json` file |
| **Export all** | Download all saved runs as JSON (backup) |
| **Clear all** | Delete every saved run (confirmation required) |

### 9.5 Re-run all saved audits (admin)

Recomputes comparison/findings for every saved run using current rules and engine logic.

---

## 10. Tariff logic — what analysts should know

### 10.1 Rate-determination date

Chapter 99 expectations use a **rate-determination date** from the 7501 extract:

1. **IT Date** (Block 17)
2. **Warehouse withdrawal date** (entry type 31)
3. **Latest release date** (Block 7)
4. Fallbacks: entry date → import date (Block 11)

The Snapshot KPI **Ch99 rules as of** shows this date and its source.

### 10.2 EU cap (ES, PT, BG)

| HTSUS Column 1 (General) rate | Expected Ch99 | Reciprocal duty |
|-------------------------------|---------------|-----------------|
| **≥ 15%** | `9903.02.19` | 0% additional |
| **&lt; 15%** (incl. Free) | `9903.02.20` | +15% additive on Ch99 line |

The engine uses the **HTS Classification Table** when loaded (not filed 7501 column 33 replacement-duty rates). Example: perfume Col-1 **Free** → expect **`9903.02.20`**.

| Window | Behavior |
|--------|----------|
| Before **2025-08-07** (or in-transit grandfather) | `9903.01.25` (10% regime) |
| **2025-08-07** → **2026-02-19** | Truth table above |
| **2026-02-20** onward | **REVIEW** — `NEEDS_REVIEW_EO14389` |

### 10.3 Section 232

Extra Ch99 rows on the same CM item are **Info**, not Critical. Separate CM-item 232 lines pair as **232 SPLIT (7501 adjunct)**. Adjunct entered values roll into the parent line before diffing.

### 10.4 Section 301 (China)

**PARTIAL** means no `9903.88.*` filed — confirm against USTR annexes.

---

## 11. Tips for playground users

### Shared data

- Runs you save are visible to **other signed-in users** on the same playground.
- Deleting a run removes it for everyone — use bulk delete carefully.
- Review sign-off and notes are team-visible.

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

### Sessions

- Stay signed in until you click **Sign out** or your session expires (typically several hours).
- If actions suddenly fail with sign-in errors, sign out and sign in again.

### Browser refresh

- **Saved or loaded audits** reopen automatically after refresh (same browser tab).
- **Unsaved new audits** (never saved to the database) cannot be restored — use **+ New Run** only after saving, or re-upload files.

### Re-run and source files

- Original **TXT/XLSX file bytes are not stored** in the database — only **filenames** and parsed line data (`raw`, `agg`, `filed`).
- **Update & re-run** (freight/insurance only) reuses saved line data; TXT **names** stay visible in the UI.
- To replace source files, use the upload zones in **Update & re-run** — do not expect the original `.txt` buffers to reload from Postgres.

---

## 12. Troubleshooting (playground)

| Symptom | What to do |
|---------|------------|
| Cannot open the app | Confirm URL with your admin; check VPN if your org requires it |
| Stuck on sign-in | Verify username/password; ask admin to reset password under **Users** |
| “Stale UI detected” banner | Hard-refresh (`Cmd+Shift+R` / `Ctrl+Shift+R`) |
| Refresh closed my audit / blank audit view | Saved runs restore on refresh; if it fails, reopen from **Dashboard** row click. Unsaved work is lost. |
| TXT filenames disappear after re-run | Fixed in current build — names are kept from saved metadata; re-upload only if replacing files |
| Dashboard empty / spinning | Hard-refresh; try again in a few minutes after a deploy |
| Loaded run shows wrong data | Click the **row** on Dashboard (not only expand) |
| Re-run didn’t change totals | Expand Inputs → **Update & re-run** → change freight/insurance |
| Old EU cap verdicts on saved runs | Ask admin: Reference → **Re-run all saved audits** |
| EU cap finding on ES Free goods | Confirm HTS table is uploaded; hard-refresh after deploy |
| HTS / Reference empty | Ask admin to upload HTS table under **Reference** |
| Import / Export / Clear missing | Admin only — **Reference → Run data management** |
| Review status not saving | Run must be saved first on new audits; hard-refresh; sign out/in; confirm you clicked **Save review** |
| Sign-off disappeared after re-run | Re-run can change findings — update status/notes if disposition changed |
| Issues column says Clean but I see Info in audit | Column prioritizes Critical/High preview; open Findings for full list |
| XLSX upload fails | Check file has **Sheet0**; try Chrome; file size under ~50 MB |
| “Wrong URL” / `file://` banner | You opened a local file — use the playground URL instead |

---

## 13. Getting help

| Need | Contact |
|------|---------|
| Login, new account, password reset | Your **KlearNow admin** (Users tab) |
| Playground URL | Your **KlearNow admin** |
| HTS table upload, rules changes, bulk re-run | **Admin** user on your team |
| Bug or feature request | Engineering via your KlearNow channel |
| Local install / developer setup | [SETUP.md](SETUP.md) — not required for playground users |

---

## Quick start checklist

- [ ] Bookmark the playground URL from your admin
- [ ] Sign in — land on Dashboard
- [ ] Confirm HTS table is loaded (Reference → admin can verify)
- [ ] **+ New Run** → upload TXT + 7501 XLSX → **Run Audit**
- [ ] Review Findings and Comparison tabs
- [ ] Review **Findings** → Comparison → sign off with status + note
- [ ] Use **Pending Review** / **Follow-up** cards to clear your queue
- [ ] Hard-refresh after any announced deploy
