# Setting up the 7501 Audit Dashboard

Get Postgres + the Flask server running so saved audits, sign-in, Reference data, and Dashboard analytics work. About 10 minutes first time.

**After setup, read [USER_MANUAL.md](USER_MANUAL.md)** for how to run audits, use Dashboard, and manage reference data.

---

## What you need

1. This repo on your Mac (or Linux)
2. **Homebrew** — `brew --version` should print a version ([brew.sh](https://brew.sh) if not)
3. **Python 3.10+**

---

## Step 1 — PostgreSQL (one-time)

```bash
brew install postgresql@16
brew services start postgresql@16
brew services list | grep postgresql   # should show "started"
```

The audit server creates the `inditex_audit` database and tables on first run.

---

## Step 2 — Python environment (one-time)

From the repo root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Dependencies: Flask, psycopg2, PyJWT, flask-cors, python-dotenv.

---

## Step 3 — Admin account (one-time)

Sign-in is required for Dashboard and Reference. Seed the first admin:

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```
INITIAL_ADMIN_PASSWORD=your-secure-password
JWT_SECRET=some-long-random-string
```

On first server start, user `admin` (or `INITIAL_ADMIN_USERNAME`) is created if the users table is empty. Add more users later under **Users** (admin only).

---

## Step 4 — Start the app

**Recommended:**

```bash
./start.sh
```

This starts Postgres if needed, launches Flask on port 5252, waits for `/api/health`, and opens your browser.

**Manual:**

```bash
source .venv/bin/activate
python3 inditex_audit_server.py
```

Then open **http://localhost:5252**.

> **Important:** Do not open `inditex_audit_dashboard.html` from Finder (`file://`). Auth, Postgres saves, and Reference sync only work over HTTP from the server.

---

## Step 5 — Sign in and verify

1. Sign in with your admin credentials
2. Top bar should show your username
3. **Dashboard** opens (may be empty until you save a run)
4. Optional: upload HTS Classification Table under **Reference** (admin)

---

## Daily use

```bash
cd /path/to/Inditex-audit-main
./start.sh
```

Sign in → run audit → **Save run** → browse history on **Dashboard**.

---

## Migrating old browser-only saves

If you previously used the HTML file without the server:

1. Open the old session (or re-import if you have a JSON export)
2. Go to **Dashboard** → **Export all** (`.json`)
3. Start the server, sign in, **Dashboard** → **Import** → select the JSON

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Sign-in fails | Check `INITIAL_ADMIN_PASSWORD` was set before first start; or reset via `psql` / create user as admin |
| `Storage: browser localStorage` | Use `http://localhost:5252`, not `file://` |
| `could not connect to server` | `brew services start postgresql@16` |
| Port 5252 in use | `PORT=5500 ./start.sh` |
| `.venv not found` | Run Step 2 |
| `Module not found` | `.venv/bin/pip install -r requirements.txt` |

### Peek at the database

```bash
psql -d inditex_audit -c "SELECT id, name, entry_num, findings_count, saved_at FROM audit_runs ORDER BY saved_at DESC LIMIT 20;"
```

### Reset all saved runs

```bash
psql -d inditex_audit -c "TRUNCATE audit_runs;"
```

---

## Playground / production

Local `./deploy.sh` targets Elastic Beanstalk and requires Terraform init in `terraform/envs/dev`.

**Standard team workflow:** sync app files to `klearnow/kn-playground` → open PR to `master` → merge → **Inditex Audit Deploy** workflow updates playground prod. See repo README.

**End users on playground:** share **[USER_MANUAL_PLAYGROUND.md](USER_MANUAL_PLAYGROUND.md)** (not this SETUP guide).

---

## Next steps

- **[USER_MANUAL.md](USER_MANUAL.md)** — full product guide
- **[BUILD.md](BUILD.md)** — architecture for developers
