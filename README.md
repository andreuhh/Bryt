# BRYT // ALPHA

Advanced endurance training monitoring: mechanical load, muscular breakdown, nutrition and
recovery, driven by a multi-agent system (Claude) on top of deterministic data.

- `backend/` — FastAPI, PostgreSQL, `.fit` parser, agents
- `frontend/` — Next.js 16, Tailwind, Recharts
- Project rules: [`CLAUDE.md`](CLAUDE.md) · Backlog: [`TODO.md`](TODO.md)

---

## Daily start

You need **three things running**: database (Docker), backend, frontend.
Every command fits on **one line**: copy it and paste it into a **separate terminal window**
(not into the Claude Code prompt).

**1. Database** — only after a Mac restart (open Docker Desktop first):

```
cd ~/Desktop/Bryt && docker compose up -d db
```

**2. Backend** — terminal 1 (agents on: real analyses with Claude):

```
cd ~/Desktop/Bryt/backend && .venv/bin/uvicorn app.main:app --reload
```

Cost per run analysis: an easy run gets the light analysis on Haiku (≈ $0.003); quality
sessions, long runs and re-analyses run in full on Opus (≈ $0.10–0.30). The coach chat and the
Sunday-evening automatic plan refinement also use credits.
Check your balance at https://console.anthropic.com

**3. Frontend** — terminal 2:

```
cd ~/Desktop/Bryt/frontend && npm run dev
```

Then open **http://localhost:3000**

To stop the backend or the frontend: `Ctrl+C` in its terminal.

### Agents off (no Claude cost, for working on the UI)

Use this instead of command 2:

```
cd ~/Desktop/Bryt/backend && AGENTS_ENABLED=false .venv/bin/uvicorn app.main:app --reload
```

Runs are still imported, with charts and metrics, but **never analyzed**: "Analizza ora" answers
"Analisi non disponibile". Restart with command 2 to analyze them.

### Runs from the watch (Intervals.icu)

Watch → Suunto app → Intervals.icu → BRYT happens on its own **while the backend is running**:
it checks Intervals.icu every 15 minutes, and again when you open the dashboard. New runs are
analyzed right away **only with agents on** (command 2); with agents off they are imported
without analysis ("Analizza ora" on the dashboard after restarting with agents on). Backend off =
nothing happens; on the next start it catches up on the last 2 days.

Do the **morning check-in** on the dashboard (hours slept + how you feel): the run analysis
uses it, so there is no need to add tags afterwards.

### After updating the code

If the database schema changed (new files in `backend/migrations/versions/`), apply it once
before starting the backend:

```
cd ~/Desktop/Bryt/backend && .venv/bin/alembic upgrade head
```

---

## First-time setup (once)

Requirements: Docker Desktop, Python 3.11+, Node.js 20+.

```
cd ~/Desktop/Bryt && docker compose up -d db
```

```
cd ~/Desktop/Bryt/backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```
cd ~/Desktop/Bryt/backend && cp .env.example .env && .venv/bin/alembic upgrade head
```

```
cd ~/Desktop/Bryt/frontend && npm install && cp .env.example .env.local
```

Then fill in the configuration files:

- `backend/.env` — `ANTHROPIC_API_KEY` (console.anthropic.com) and `ENCRYPTION_KEY`, generated with:

  ```
  cd ~/Desktop/Bryt/backend && .venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

- `backend/.env` — `SUPABASE_URL` (Supabase → Project Settings → API Keys): the backend verifies
  login tokens against it.
- `frontend/.env.local` — `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`
  (same page). With both empty the app skips the login and uses the local development user
  `NEXT_PUBLIC_DEV_USER_ID`.
- Supabase → Authentication → URL Configuration: Site URL `http://localhost:3000`, Redirect URLs
  `http://localhost:3000/**`.

### Moving data to your Supabase account

Data created before the login existed belongs to the development user. Sign in once, copy your
user id (Supabase → Authentication → Users), then:

```
cd ~/Desktop/Bryt/backend
.venv/bin/python -m scripts.reassign_user --from 11111111-1111-1111-1111-111111111111 --to <your user id>
.venv/bin/python -m scripts.reassign_user --from 11111111-1111-1111-1111-111111111111 --to <your user id> --apply
```

The first command is a dry run that only lists what would move.

---

## Troubleshooting

**"Address already in use" / port busy** — a server is already running. To see who uses the port:

```
lsof -nP -iTCP:3000 -sTCP:LISTEN
```

(replace `3000` with `8000` for the backend), then stop it with `Ctrl+C` in its terminal.

**A visual change does not show up** — stop the frontend (`Ctrl+C`) and run `npm run dev` again.

**The dashboard says the backend is unreachable** — the backend is not running (command 2).

**Database connection error** — Docker Desktop is closed or the database is down (command 1).

**The backend stops at startup with "ENCRYPTION_KEY is missing"** — set `ENCRYPTION_KEY` in
`backend/.env` (generation command in "First-time setup"). Never change it afterwards: it decrypts
the Intervals.icu keys saved in the database.

---

## Checks and tests

```
cd ~/Desktop/Bryt/backend && .venv/bin/pytest -q && .venv/bin/ruff check app tests && .venv/bin/mypy app
```

```
cd ~/Desktop/Bryt/frontend && npm run typecheck && npm run lint && npm run build
```

After changing backend schemas, regenerate the frontend types:

```
cd ~/Desktop/Bryt/backend && .venv/bin/python -m scripts.export_openapi && cd ../frontend && npm run gen:api
```
