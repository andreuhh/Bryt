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

**2. Backend** — terminal 1 (agents off: no cost):

```
cd ~/Desktop/Bryt/backend && AGENTS_ENABLED=false .venv/bin/uvicorn app.main:app --reload
```

**3. Frontend** — terminal 2:

```
cd ~/Desktop/Bryt/frontend && npm run dev
```

Then open **http://localhost:3000**

To stop the backend or the frontend: `Ctrl+C` in its terminal.

### Agents on (real analyses with Claude, ~$0.30 per run)

Use this instead of command 2:

```
cd ~/Desktop/Bryt/backend && .venv/bin/uvicorn app.main:app --reload
```

With agents on, the Sunday-evening automatic plan refinement also uses credits.
Check your balance at https://console.anthropic.com

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
