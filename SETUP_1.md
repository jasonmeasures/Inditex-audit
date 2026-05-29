# Setting up the 7501 Audit Dashboard for persistent saves

This walks through getting the dashboard running with a local Postgres backend so your saved audit runs persist forever. About 10 minutes from start to finish.

## What you need before starting

1. **A folder** containing both files together:
   - `inditex_audit_dashboard.html`
   - `inditex_audit_server.py`
2. **Homebrew** installed on your Mac. Check by opening Terminal and running:
   ```bash
   brew --version
   ```
   If that prints a version, you're good. If not, install it from https://brew.sh first.

---

## Step 1 — Install Postgres (one-time, ~3 minutes)

In Terminal:

```bash
brew install postgresql@16
```

When it finishes, start it:

```bash
brew services start postgresql@16
```

Confirm it's running:

```bash
brew services list | grep postgresql
```

You should see `postgresql@16  started`.

That's it for Postgres. You never need to touch it again — the audit server creates its own database on first run.

---

## Step 2 — Install Python dependencies (one-time, ~30 seconds)

Still in Terminal:

```bash
pip3 install flask psycopg2-binary
```

If `pip3` says "command not found," your Mac doesn't have Python yet. Run:

```bash
brew install python
```

Then retry the `pip3 install` line.

---

## Step 3 — Run the audit server

In Terminal, navigate to the folder where you keep `inditex_audit_dashboard.html` and `inditex_audit_server.py`. Example, if they're in your Downloads folder:

```bash
cd ~/Downloads
```

Then start the server:

```bash
python3 inditex_audit_server.py
```

You should see output like:

```
📊 Inditex Audit Server
   Database: postgres://YOUR_USER@localhost:5432/inditex_audit
   Dashboard: /Users/YOUR_USER/Downloads/inditex_audit_dashboard.html
  • Database 'inditex_audit' not found, creating...
  • Created database 'inditex_audit'
  • Schema ready (table: audit_runs)

🚀 Open http://localhost:5252 in your browser
   (Ctrl-C to stop)
```

The "creating database" line only appears once. Every future startup will skip it.

**Leave this Terminal window open.** Closing it stops the server.

---

## Step 4 — Open the dashboard the right way

Open your browser and go to:

```
http://localhost:5252
```

**Important:** don't open the .html file directly from Finder anymore. The dashboard only sees the Postgres backend when it's loaded over `http://localhost:5252`, not from a `file://` URL.

Go to the **Saved Runs** tab. The Storage indicator at the top should now read:

```
Storage: Database · connected
```

You should also see the red "Browser storage is full" banner disappear.

---

## Step 5 — Recover your previous saves (if you want them)

Before the switch you had 2 runs visible in browser localStorage. To bring them across:

1. On the dashboard, click **Export to JSON** in the Saved Runs tab. That downloads a `.json` file with whatever runs are currently in localStorage.
2. Click **Clear browser storage** (in the red banner, or from "Clear all" if the banner's already gone). This evicts the fat legacy snapshots stuck in localStorage.
3. Click **Import** and select the `.json` you just downloaded. The dashboard POSTs each run to the Postgres server individually.

After that the runs live in Postgres, not localStorage, and they're durable.

---

## Daily use

Every time you sit down to use the dashboard:

1. Open Terminal.
2. `cd` to the folder with the files (e.g. `cd ~/Downloads`).
3. Run `python3 inditex_audit_server.py`.
4. Open `http://localhost:5252` in your browser.

If you want it always-on, you can let it run in the background — Postgres uses near-zero CPU when idle and the Flask server is about 30 MB of RAM.

---

## Troubleshooting

**"Storage: browser localStorage" still shows after Step 4.**
The dashboard is connecting to `file://` not `http://localhost:5252`. Close the tab and type `http://localhost:5252` directly into the address bar.

**"could not connect to server" when starting the audit server.**
Postgres isn't running. Run `brew services start postgresql@16` and try again.

**"role 'YOUR_USER' does not exist" or auth errors.**
Postgres uses your Mac username by default. If you installed Postgres differently in the past, set the user explicitly:

```bash
PGUSER=postgres python3 inditex_audit_server.py
```

**Port 5252 already in use.**
Something else is using that port. Pick another:

```bash
PORT=5500 python3 inditex_audit_server.py
```

Then open `http://localhost:5500`.

**"Module not found: flask" or similar.**
The `pip3 install` from Step 2 didn't actually run, or you have multiple Python versions. Try:

```bash
python3 -m pip install flask psycopg2-binary
```

---

## What's in the database

If you ever want to peek directly:

```bash
psql -d inditex_audit -c "SELECT id, name, entry_num, agg_lines, findings_count, saved_at FROM audit_runs ORDER BY saved_at DESC;"
```

To wipe everything and start over:

```bash
psql -d inditex_audit -c "TRUNCATE audit_runs;"
```

To delete the database entirely:

```bash
dropdb inditex_audit
```

The audit server will recreate it on next startup.
