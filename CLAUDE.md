# BRYT — Project Rules

**BRYT** (norvegese *å bryte*: rompere/superare i propri limiti) è una web app multi-tenant per il
monitoraggio avanzato di allenamento endurance, carico meccanico, nutrizione e recupero, basata su
un'architettura **Multi-Agent deterministica**. Target: runner/atleti endurance evoluti con
background eterogenei (Strada, Trail, Pista/Mezzofondo).

Queste regole sono vincolanti per ogni modifica al codice.

---

## 1. Monorepo

```
/frontend   Next.js 16 (App Router, Turbopack), TypeScript, Tailwind CSS v4 puro, Recharts
/backend    Python 3.11+, FastAPI, SQLModel, Pydantic v2, fitparse, pandas, httpx, Anthropic SDK
docker-compose.yml   PostgreSQL 16 locale (prod: Supabase-compatibile)
```

### Comandi
`.venv/bin/python -m scripts.recompute_metrics [--user <uuid>]` ricalcola `computed_metrics`
dai `.fit` salvati dopo una modifica all'analisi deterministica.

```bash
docker compose up -d db                                   # Postgres locale
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload                   # API → http://localhost:8000/api/v1
.venv/bin/alembic upgrade head                            # applica le migrazioni
.venv/bin/alembic revision --autogenerate -m "..."         # dopo ogni modifica ai modelli
.venv/bin/pytest && .venv/bin/ruff check app tests migrations && .venv/bin/mypy app
cd frontend && npm install && npm run dev                 # UI  → http://localhost:3000
npm run build && npm run lint
```

### Backend layout (`backend/app`)
| Cartella    | Responsabilità |
|-------------|----------------|
| `api/v1/`   | Router FastAPI sottili. Un modulo per dominio in `endpoints/`, registrato in `router.py`. Nessuna logica di business. |
| `core/`     | Settings (`pydantic-settings`), engine/sessione async DB, cifratura segreti (Fernet). |
| `models/`   | Tabelle SQLModel (Shared State PostgreSQL). |
| `schemas/`  | Modelli Pydantic: contratti API e **output strutturati degli Agent**. |
| `services/` | Logica **deterministica**: parser `.fit`, sync Intervals.icu, calcolo metriche. Nessuna chiamata LLM. |
| `agents/`   | I tre Agent + orchestratore della pipeline. Unico layer che chiama l'LLM. |

### Frontend layout (`frontend/src`)
| Cartella                | Responsabilità |
|-------------------------|----------------|
| `app/`                  | Rotte App Router. |
| `components/ui/`        | Primitive custom (Card, Pill, Metric, …). |
| `components/brand/`     | Wordmark e identità. |
| `components/charts/`    | Wrapper Recharts minimalisti. |
| `components/plan/`, `components/shell/` | Viste per area (es. `PlanView`) e guscio (`AppShell`, `ThemeToggle`). |
| `lib/`                  | Client API, formatter (passo, durata), utility. |
| `types/`                | Tipi TS speculari agli schemi Pydantic. |

### Frontend: regole di implementazione
- **Tipi generati, mai scritti a mano**: `backend/.venv/bin/python -m scripts.export_openapi`
  (da `backend/`) → `frontend/openapi.json` → `npm run gen:api` → `src/types/api.ts`. Rigenerare a
  ogni modifica degli schemi Pydantic. Alias leggibili in `src/lib/types.ts`.
- **Client API** `src/lib/api.ts` (`openapi-fetch`, tipizzato): unico punto di autenticazione
  (`Authorization: Bearer <token Supabase>` se `NEXT_PUBLIC_SUPABASE_URL`/`_PUBLISHABLE_KEY` sono
  impostati, altrimenti `X-Dev-User-Id` da `NEXT_PUBLIC_DEV_USER_ID`). `unwrap()` converte gli
  errori in `ApiError(status)`.
- **Auth** (`lib/auth.ts`): Supabase solo lato browser (email + password), sessione in
  supabase-js; `AuthGate` protegge `(app)` e `/onboarding` → `/login?next=…`. Senza profilo,
  `RequireProfile` porta a `/onboarding`; `/settings` (per ora solo Intervals.icu + account); con un piano attivo `/onboarding` rimanda a `/dashboard`.
  Al logout e al cambio utente: `queryClient.clear()` e rimozione dei dati locali per utente (chat, bozza
  onboarding). `scripts.reassign_user` sposta i dati dall'utente di sviluppo a un account reale.
- **Dati utente lato client** con TanStack Query (`src/lib/queries.ts`, chiavi in `keys`); le
  pagine sono gusci statici che montano una vista client (`components/<area>/<Area>View.tsx`).
- **Cache Components**: niente `new Date()` durante il prerender. La data di oggi si legge con
  `useToday()` (`src/lib/hooks.ts`, `null` sul server → stato di caricamento). Formattazione
  date/numeri solo in `src/lib/format.ts` (it-IT, Europe/Rome; mesi minuscoli,
  `first-letter:uppercase` invece di `capitalize`).
- **Tema**: scuro di default; script inline in `<head>` (`THEME_SCRIPT`) applica la scelta
  salvata (`localStorage["bryt-theme"]`) prima del primo paint.
- **Grafici** (Recharts): colori solo da token `--bryt-chart-*` (validati con il checker
  dataviz contro le superfici; l'accento brand è troppo chiaro per le barre in dark mode);
  barre ≤ 24 px con estremità arrotondate 4 px; griglia solo orizzontale, sottile; tooltip
  flottante custom; legenda sempre presente con ≥ 2 serie; testi in colori testo, mai della
  serie. **Mai due assi Y**: passo/FC/cadenza sono grafici impilati con cursore sincronizzato.
- **Telemetria** (`lib/activity.ts`): passo levigato tramite la velocità (media mobile), asse
  del passo invertito, dominio robusto (percentili 2-98) per ignorare soste e scatti; distanze
  mancanti nei file (alcuni dispositivi) riportate in avanti, mai a 0. Le bande grigie sono i
  tratti confrontati dall'analisi di divergenza (`computed_metrics.cadence_hr_divergence`).
- `/activity/[id]` legge l'id con `useParams` sotto `<Suspense>` (rotta dinamica). Gli output
  degli agent arrivano tipizzati dal report; feedback 👍/👎 (commento facoltativo sul 👎).
- Componenti custom in `components/ui` (Button, Badge, Card, Pill, Metric, Modal su
  `<dialog>`, SegmentedControl, States) e icone inline in `components/icons.tsx`.
- **Upload dalla dashboard = una sola analisi**: upload con `analyze=false` → modale tag →
  "Salva e analizza" (`PATCH /context`, avvia la pipeline) oppure "Salta" (`analyze?background=true`).
  Chiudere la modale non avvia nulla (la card "Ultima analisi" offre "Analizza ora"). La sync
  Intervals analizza subito (nessun tag). Il report (`GET /report`) espone gli output tipizzati
  degli agent; il client fa polling solo dopo aver avviato lui la pipeline.
- **Tag modificati dopo** (pagina attività, modale in modalità `edit`): "Salva" è disattivato se
  nulla cambia (confronto per valore); salvare rifà l'analisi (`PATCH /context?analyze=true`)
  finché il tetto lo consente, poi salva soltanto. La superficie è inviata solo se l'atleta la
  cambia (altrimenti una superficie `PROFILE_DEFAULT` diventerebbe `USER`, cioè "certa").
- **Tetto analisi per corsa**: `MAX_ANALYSES_PER_ACTIVITY` (default 2 = prima analisi + una
  rianalisi) sulle analisi richieste dall'atleta (`/analyze`, `PATCH /context?analyze=true` → 429
  oltre il tetto); `GET /report` espone `analyses_left`. Le analisi fallite non contano.
- **Check-in mattutino** (`CheckInCard` in cima alla dashboard): ore dormite + come ti senti
  (emoji 1-5), ogni tocco salva, compilato si riduce a una riga. Facoltativo, nessun promemoria.
  Pre-compila il sonno nella modale dei tag. Agli agent arriva `wellness`
  (`services/wellness.wellness_summary`: check-in del giorno, media ultimi 7 giorni vs i 28
  precedenti) in analisi, nutrizione, chat e aggiornamento settimanale.
- **Sync all'apertura**: la dashboard lancia una sync se l'ultima (`intervals_synced_at`) ha più
  di 10'; le corse nuove vengono seguite nella card "Ultima analisi".
- **Chat** (`/chat`): stateless lato backend; la conversazione vive nel client (`localStorage["bryt-chat"]`,
  ultimi 40 messaggi inviati a ogni turno, vedi `lib/chat.ts`). La `proposed_adjustment` del coach è
  una card "Applica al piano" (`POST /plans/adjust`) / "Non ora": mai applicata senza conferma.
  Risposte in testo semplice (niente markdown, regola nel prompt).
  Guardrail costi: `CHAT_DAILY_LIMIT` risposte riuscite per giorno locale (oltre → 429 senza chiamare
  l'LLM); tutto lo shared state è nel prefisso in cache, quindi i turni successivi lo rileggono.
- Errori: "nessun piano" solo su 404; ogni altro errore (anche backend irraggiungibile) mostra
  `ErrorState` con "Riprova".
- Verifica visiva: build di produzione + screenshot (desktop e viewport mobile emulato via
  Chrome DevTools Protocol: Chrome headless ha una larghezza minima di finestra).

> **Next.js 16**: API e convenzioni differiscono dalle versioni precedenti. Prima di usare API
> Next.js, consultare `frontend/node_modules/next/dist/docs/` (vedi `frontend/AGENTS.md`).
> `cacheComponents` e `partialPrefetching` sono attivi in `next.config.ts`.

---

## 2. Regole architetturali

1. **Multi-tenant obbligatorio**: ogni tabella di dominio ha `user_id` indicizzato; ogni query
   filtra per `user_id` dell'utente autenticato. Mai query cross-tenant.
2. **Separazione deterministico / AI**: parsing, metriche, zone e soglie sono calcolati in
   `services/` con codice puro e testabile. Gli Agent **interpretano** numeri già calcolati,
   non li calcolano.
3. **Agent senza conversazione libera**: comunicano solo tramite lo **Shared State** su
   PostgreSQL e output JSON validati da **Pydantic** (Structured Outputs Anthropic). Ogni
   esecuzione è persistita in `AgentExecutionLog` (input, output, modello, feedback 👍/👎).
4. **Segreti cifrati**: `intervals_api_key` è salvata solo cifrata (`core/security.py`), mai
   loggata né restituita dalle API.
5. **Async ovunque** nel backend (FastAPI, SQLAlchemy async/asyncpg, httpx.AsyncClient).
6. **Nessun valore fisiologico hardcoded** (vedi §5).
7. Modello LLM configurabile via `ANTHROPIC_MODEL` (default `claude-opus-5-5`), con override per
   agent (`<AGENT>_MODEL`, `Settings.model_for`): `NUTRITION_RECOVERY_MODEL=claude-haiku-5-5`,
   `COACH_CHAT_MODEL=claude-sonnet-5-5`; analisi meccanica e piano restano su Opus (scelta fatta
   con un confronto affiancato su input reali). Il modello usato è salvato nel log.

### Modello dati (Shared State)

| Tabella | Note |
|---------|------|
| `users` | `id` = UUID di **Supabase Auth** (`auth.users.id`), mai generato dal backend |
| `user_lifestyle_profiles` | 1:1 con user (`UNIQUE user_id`). Volume abituale (obbligatorio) e di picco, forza (`strength_sessions_per_week` + `strength_setting` NONE/HOME/GYM), `double_sessions_ok`, `long_run_day`, `hr_sensor`, `injury_notes`, `coach_notes` (testo libero letto dagli agent). API key Intervals solo in `intervals_api_key_encrypted` |
| `personal_bests` | una riga per PB (storico): la calibrazione pesa i PB **recenti** |
| `training_plans` | `GENERATING`→`ACTIVE` (o `FAILED` + `generation_error`); `blocks` JSONB = `list[PlanBlock]`; `last_refined_on` |
| `workouts` | `PLANNED`/`COMPLETED`/`MODIFIED`; `detail_level` `CONFIRMED`/`PROVISIONAL`; `is_key_session`; `structure` JSONB = `list[WorkoutStep]`; `original_snapshot` = prima versione |
| `workout_revisions` | cronologia (`APPLIED`) e proposte (`PENDING` → `APPLIED`/`REJECTED`/`SUPERSEDED`) con `before`/`after` = `WorkoutDraft` e `reason` |
| `activities` | dedup `UNIQUE(user_id, source, external_id)` e `UNIQUE(user_id, fit_sha256)`; `context_tags` JSONB = `ContextTags` |
| `activity_streams` | serie temporali 1:1 con activity, array allineati su `elapsed_s` |
| `daily_wellness` | check-in mattutino: `UNIQUE(user_id, day)`, `sleep_hours` (fasce: 5 = ≤5, 9 = 9+), `feeling` 1-5; entrambi facoltativi (mancante = sconosciuto) |
| `agent_execution_logs` | input/output JSON, `pipeline_run_id` per la cascata, feedback 👍/👎 |

Regole:
- Tabelle in `app/models/`, mixin in `base.py` (`IdMixin`, `TimestampMixin`, `TenantMixin`).
  Ogni tabella di dominio eredita `TenantMixin` (`user_id` FK `users.id` `ON DELETE CASCADE`).
- **Enum come VARCHAR** (`enum_column()`), mai tipi enum nativi PG. Enum in `app/models/enums.py`.
- **La forma dei JSONB è definita in `app/schemas/`**: validare con Pydantic prima di scrivere.
- Niente `Relationship()` SQLModel (lazy loading incompatibile con async): query esplicite
  sempre filtrate per `user_id`.
- Ogni modifica ai modelli → nuova migrazione Alembic; `alembic check` deve restare pulito.
- Schemi: `StrictModel` (`extra="forbid"`) per input e output agent, `ORMModel`
  (`from_attributes`) per le letture. La API key è `SecretStr` in input e non compare in alcun
  `*Read` (solo `intervals_connected: bool`).
- Output agent in `app/schemas/agents.py`: `PlanGenerationOutput`, `PlanAdjustmentOutput`,
  `MechanicalLoadOutput`, `NutritionRecoveryOutput` (bipartito). Coerenza garantita da
  validator (es. `plan_adjustment_needed=true` ⇔ `adjustment_request` presente).

---

## 3. Pipeline Multi-Agent

```
Onboarding ─► TrainingPeriodizationAgent ─► TrainingPlan + Workout (PLANNED)

Nuova attività (.fit) ─► fit_parser (deterministico) ─► Activity
      └─► MechanicalLoadAgent ─► { flags, plan_adjustment_needed, ... }
             ├─ if plan_adjustment_needed ─► TrainingPeriodizationAgent (rimodula 3-4 giorni → MODIFIED)
             └─► NutritionRecoveryAgent ─► { nutrition_protocol, recovery_protocol }
```

- **TrainingPeriodizationAgent**
  - *Onboarding*: non genera alcun piano senza profilo completo: background, PB attuali, gara
    obiettivo, abitudini orarie (mattina/pausa pranzo/sera), giorni disponibili, tipo di lavoro
    (sedentario/fisico), ore di sonno, accesso ai terreni.
  - *Adattivo*: se `plan_adjustment_needed == true`, rimodula i 3-4 giorni successivi.
  - Supporta metodologie avanzate: **Double Threshold** norvegese, periodizzazione a blocchi,
    settimane di carico/scarico.
- **MechanicalLoadAgent**: post-parsing. Confronta eseguito vs pianificato, stress meccanico
  relativo al background, *Cadence vs HR Divergence*, fattori contestuali. Output JSON con flag.
- **Coach chat** (`AgentName.COACH_CHAT`): risponde sullo shared state; può solo *proporre*
  una modifica (`proposed_adjustment`), applicata solo dopo conferma via `POST /plans/adjust`.
- **NutritionRecoveryAgent**: unico agent con output **bipartito**:
  - `nutrition_protocol`: carboidrati, proteine per riparazione muscolare, elettroliti, timing
    caffeina rispetto all'orario di corsa.
  - `recovery_protocol`: sonno, mobilità, gestione jet lag/stress.

### Endpoint
| Metodo | Path | Step |
|--------|------|------|
| GET  | `/api/v1/health` | 1 ✅ |
| GET  | `/api/v1/me`, `/api/v1/me/profile`, `/api/v1/me/calibration` (zone) | 3-4 ✅ |
| PATCH | `/api/v1/me/profile` (modifica parziale, pagina impostazioni) | 4 ✅ |
| PUT  | `/api/v1/me/onboarding` (profilo + PB + credenziali Intervals verificate live) | 3 ✅ |
| POST | `/api/v1/integrations/intervals/sync` (`analyze=false` = import dello storico senza agent, nessun costo LLM) | 3 ✅ |
| POST | `/api/v1/integrations/intervals/webhook` (pubblico, autenticato dal `secret`) | 3 ✅ |
| POST | `/api/v1/activities/upload-fit` (201 nuovo / 200 già presente) | 3 ✅ |
| POST | `/api/v1/plans/generate` → **202** `GENERATING`, job in background; polling `GET /plans/{id}` | 4 ✅ |
| GET  | `/api/v1/plans/active`, `/api/v1/workouts?from=&to=&key_only=` (calendario / sessioni chiave) | 4 ✅ |
| POST | `/api/v1/plans/active/refine` (aggiornamento settimanale manuale) | 4 ✅ |
| GET  | `/api/v1/plans/active/proposals`; POST `/plans/proposals/{id}/accept\|reject` | 4 ✅ |
| GET  | `/api/v1/workouts/{id}/history` (perché una sessione è cambiata) | 4 ✅ |
| POST | `/api/v1/plans/adjust` (conferma la proposta della chat) | 4 ✅ |
| POST | `/api/v1/chat` (stateless: il client invia la conversazione) | 4 ✅ |
| GET  | `/api/v1/wellness?from=&to=`; PUT `/api/v1/wellness/{day}` (check-in, oggi e 7 giorni prima) | 5 ✅ |
| GET  | `/api/v1/chat/quota` (messaggi rimasti oggi; `CHAT_DAILY_LIMIT`, default 15) | 5 ✅ |
| GET  | `/api/v1/activities`, `/{id}`, `/{id}/streams`, `/{id}/report` | 4 ✅ |
| PATCH | `/api/v1/activities/{id}/context` (tag; `?analyze=true` avvia la pipeline, altrimenti solo salvataggio) | 5 ✅ |
| POST | `/api/v1/activities/{id}/analyze` (sincrona; `?background=true` → 202 + polling del report) | 4-5 ✅ |
| POST | `/api/v1/activities/upload-fit?analyze=false` (la dashboard raccoglie prima i tag) | 5 ✅ |
| POST | `/api/v1/agent-runs/{id}/feedback` (👍/👎) | 4 ✅ |

### Implementazione agent (`app/agents/`)
- `llm.py`: `LLMClient` protocol + `AnthropicLLM` (`client.beta.messages.stream`,
  `output_format=<Pydantic>`, `thinking: adaptive`, `output_config.effort` esplicito,
  `cache_control` automatico, refusal fallback server-side `fallbacks="default"` + beta
  `server-side-fallback-2026-07-01`, non su Haiku). Errori → `AgentUnavailableError` (503),
  `AgentRefusalError` (422), `AgentOutputError`/`AgentError` (502).
- `runner.py`: unico punto di chiamata. Ogni esecuzione → riga `AgentExecutionLog` (anche in
  errore). Validator deterministici di dominio (giorni disponibili, zone esistenti, finestra
  date, id dei workout, alert di breakdown coerente) → **un** retry con le violazioni come feedback.
- `prompts.py`: system prompt statici. Testo per l'atleta in italiano.
- **Cache**: il turno utente ha due blocchi: `<athlete_context>` stabile (profilo, PB, zone;
  per i blocchi del piano anche lo scheletro) con breakpoint `cache_control`, poi task +
  `<context>` variabile. Chiamate della stessa esecuzione rileggono il prefisso. JSON con
  chiavi ordinate (byte-identico). Nel log: `input_tokens`, `cache_creation_input_tokens`,
  `cache_read_input_tokens`, `output_tokens` (prezzi diversi).
- `context.py`: viste read-only dello shared state (mai la API key Intervals).
- `pipeline.py`: cascata post-attività con `pipeline_run_id` condiviso. Lanciata in
  background (`get_pipeline_launcher`, disattivabile con `AGENTS_ENABLED=false`) dopo upload,
  sync Intervals, webhook e aggiornamento dei tag.
- Effort: scheletro e refinement `high`; blocchi, analisi, adattamento, nutrizione `medium`;
  chat `low`.
- Regole calendario (validator): giorni disponibili per le corse (la forza `STRENGTH` è
  esente e non conta come corsa); max 1 corsa al giorno, 2 (AM/PM) solo con
  `double_sessions_ok`; **max 2 sessioni chiave a settimana** (solo lunghi, passo gara,
  test, gare: la doppia soglia non è mai chiave).
- **Piano a orizzonte completo** (`training_periodization.py`):
  1. generazione in background: fase 1 *scheletro* (blocchi contigui fino al giorno gara, volume
     target per settimana), fase 2 *un blocco alla volta* con **ogni giorno** (REST espliciti),
     continuità passata dall'ultima settimana del blocco precedente. In caso di errore il piano
     va in `FAILED`, i suoi workout sono rimossi e il piano attivo precedente resta valido;
  2. `detail_level` deciso dal **codice** in base alla data (`services/workouts.py`,
     `CONFIRM_DAYS = 14`): oltre la finestra i workout sono `PROVISIONAL` e passi/FC esatti
     vengono rimossi (restano zone, distanza/durata, `is_key_session`);
  3. **aggiornamento settimanale** (domenica ≥ 20:00 ora locale dell'atleta, recupero se
     saltato ≥ 7 giorni): conferma i provvisori dei prossimi 14 giorni con i dati attuali;
     sulle sessioni chiave più lontane solo **proposte** `PENDING`, applicate se l'atleta accetta;
  4. ogni modifica materiale (post-attività, chat, refinement, proposta accettata) → riga
     `workout_revisions` `APPLIED` con motivazione.
- **Scheduler** (`agents/scheduler.py`): task asyncio nel lifespan dell'app, tick ogni
  `SCHEDULER_INTERVAL_S`; ogni piano viene *claimato* con UPDATE condizionale atomico su
  `last_refined_on` (sicuro con più istanze). `SCHEDULER_ENABLED=false` nei test.
- Test: `tests/agent_fakes.FakeLLM` (nessuna chiamata di rete nei test).

### Servizi deterministici di contesto
- `services/calibration.py`: soglia ≈ passo sostenibile 60' dai PB (Riegel, esponente 1.06).
  PB vecchi **penalizzati, non scartati**: +0,4% sul passo per mese oltre i 6 (max +8%);
  vince la stima migliore (le maratone limitate dal cedimento muscolare sottostimano il
  motore aerobico). `confidence` HIGH (≤ 6 mesi) / MEDIUM (≤ 12) / LOW → il piano inserisce
  presto un test di ricalibrazione. Esposta da `GET /me/calibration`. Zone Friel (% FC soglia / % passo soglia) + zona `DT`
  (double threshold, sotto LT2). FC soglia stimata al 90% della FC max se assente.
- `services/history.py`: baseline 28 giorni (volume, passo, cadenza, superfici, rapporto
  acuto:cronico). `data_coverage` giudicata sulle **8 settimane** (`HABITUAL_DAYS`): LOW (< 8
  corse o km registrati < 50% del dichiarato) → `effective_weekly_km` = volume dichiarato e
  rapporto acuto:cronico non calcolato; HIGH con 4 settimane basse = calo **reale** (scarico,
  gara, recupero), non dati mancanti. Agli agent anche `habitual_weekly_km`, `weekly_km` (8
  settimane) e `recent_races` (tabella PB, che tiene anche le gare non PB, + workout `RACE`
  completati; recupero ≈ 1 giorno per miglio → `in_post_race_recovery`).
  `elevation_quality`: totali del dispositivo vs dislivello ricalcolato dalla
  serie: se incoerenti → altitudine non affidabile, es. GPS senza barometro.

### Autenticazione (`app/core/auth.py`, `app/api/deps.py`)
- Produzione: `Authorization: Bearer <access token Supabase>`, verificato via JWKS
  (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`, audience `authenticated`); HS256 solo se
  `SUPABASE_JWT_SECRET` è impostato (progetti legacy).
- Sviluppo (`ENVIRONMENT=development`): header `X-Dev-User-Id: <uuid>`. Disattivato altrove.
- `CurrentUser` crea la riga `users` al primo accesso. Ogni endpoint di dominio usa
  `CurrentUser` e filtra per `user.id`.

---

## 4. Ingestione dati (costo zero)

1. **Intervals.icu (primario)**
   - Onboarding: l'utente inserisce **Athlete ID** (es. `i12345`) e **API Key** personale
     (Intervals.icu → Settings → Developer Settings).
   - Auth: **HTTP Basic**, username letterale `API_KEY`, password = chiave dell'utente
     (Bearer con la API key personale → 403).
   - `GET /athlete/{id}/activities?oldest=YYYY-MM-DD&newest=YYYY-MM-DD` per la lista.
   - `GET /activity/{id}/file` = file **originale** (gzip; può essere fit/gpx/tcx): usato se
     `file_type == "fit"`. Altrimenti `GET /activity/{id}/fit-file` (FIT rigenerato da Intervals).
   - Tipi importati: `Run`, `TrailRun`, `VirtualRun`. Le attività di origine **Strava** non
     hanno file via API (ToS Strava) → `NO_FILE`.
   - **Sync automatica**: con le API key personali niente webhook → `agents/scheduler.py`
     `intervals_poll_loop` ogni `INTERVALS_POLL_INTERVAL_S` (900 s; `INTERVALS_POLL_ENABLED`),
     finestra ultimi 2 giorni, claim atomico su `intervals_synced_at`, analisi subito se
     `AGENTS_ENABLED`, altrimenti solo import (il protocollo post-corsa serve ora; con la
     doppia soglia l'analisi AM arriva prima della PM).
     Più sync all'apertura della dashboard e pulsante manuale (`services/intervals_sync.sync_user`).
   - **Webhook**: configurabili solo per un'app Intervals.icu registrata (OAuth). Payload
     `{secret, events:[{athlete_id, type, activity}]}`; eventi `ACTIVITY_UPLOADED`/
     `ACTIVITY_ANALYZED`; rispondere sempre 2xx velocemente (Intervals ritenta), lavoro in
     background. Activity webhook non inviati per attività Strava.
   - Dedup: `UNIQUE(user_id, source, external_id)` + hash del file + **stessa corsa da un altro
     canale** (inizio registrazione entro ±2', es. export Strava caricato a mano e copia
     Intervals: byte diversi); sync idempotente.
2. **Upload manuale `.fit` (fallback universale)**: `.fit`, `.fit.gz` o `.zip` di Garmin
   Connect ("Esporta originale"), Coros, Strava. Stesso parser, stessa pipeline.

Pipeline unica (`services/ingestion.py`): estrazione FIT (`fit_files.py`, decompressione
limitata) → hash/dedup → `fit_parser.parse_fit` (in thread) → file su storage
(`fit/{user_id}/{sha256}.fit`) → `Activity` + `ActivityStream` (≤ 3000 punti) → collega il
`Workout` PLANNED dello stesso giorno locale (AM/PM per Double Threshold) → `COMPLETED`.

Superficie (`Activity.surface` + `surface_source`): tag dell'atleta (`USER`) > modalità
dell'orologio nel `.fit` (`DEVICE`: trail/pista/tapis roulant/strada) > per una "Corsa" generica
la superficie abituale del profilo (`default_run_surface` ASPHALT/GRAVEL/MIXED →
`PROFILE_DEFAULT`, probabile); altrimenti `null` (sconosciuta, mai assumere asfalto). Cambiare la
superficie abituale aggiorna le corse `PROFILE_DEFAULT`/sconosciute, mai quelle `USER`/`DEVICE`.

Serie estratte dal `.fit`: `timestamp, pace, heart_rate, cadence, elevation, ground_contact_time`.
La cadenza FIT di corsa è in passi per gamba (strides/min): convertita in **spm** (×2).

---

## 5. Regole fisiologiche (Sport Science)

1. **Calibrazione dinamica**: zone FC, passi target e soglie di allarme sono **sempre derivati**
   da PB recenti, FC di soglia e background dichiarato (Strada / Trail / Pista-Mezzofondo).
   Nessun ritmo o FC hardcoded nel codice o nei prompt.
2. **Impatto meccanico**: il carico muscolare/eccentrico tiene conto della superficie
   (asfalto vs sterrato, dislivello negativo) e dell'incremento di velocità rispetto allo
   storico dell'atleta (un trail runner su asfalto veloce = stress elevato).
3. **Cadence vs HR Divergence → *Cedimento Meccanico Muscolare***: nei lunghi e nei lavori di
   qualità, se nella frazione finale la FC resta stabile nella zona target dell'atleta ma la
   cadenza cala di **oltre 4-5 passi/min** (o il tempo di contatto al suolo aumenta), segnalare
   cedimento meccanico anche in assenza di deriva cardiaca. Calcolo deterministico in
   `services/fit_parser.py` (`DivergenceThresholds`), interpretazione nel `MechanicalLoadAgent`:
   - campioni in movimento (≥ 1 m/s), valutazione solo oltre 20' di moving time;
   - baseline = 10-50% del moving time (salta il riscaldamento), finale = ultimo 20%;
   - sessioni variabili (CV velocità > 0.15, ripetute) → confronto solo sui campioni "work";
   - `mechanical_breakdown` = (calo cadenza > 4 spm **o** GCT +4% **o** lunghezza del passo
     -8%) **e** FC stabile (±3%) oppure, se fornita, FC finale dentro la zona target.
     La lunghezza del passo (velocità / cadenza) cattura chi mantiene la cadenza ma perde
     propulsione (caso reale: NYC Marathon, passo 1,28 → 1,05 m con cadenza e FC piatte) e
     funziona anche su orologi senza running dynamics;
   - FC stabile/in calo con forte perdita di passo = affaticamento periferico, non deriva
     cardiaca (anche se l'aerobic decoupling risulta alto);
   - calcolato anche l'aerobic decoupling (Pa:Hr) per distinguere la deriva cardiaca.
4. **Anomalie contestuali**: incrociare FC anomala a passo lento con jet lag/viaggi, caffeina
   pre-corsa, qualità del sonno → evitare falsi allarmi di calo di forma.
5. **Metodologie avanzate**: Double Threshold (scuola norvegese, soglia controllata da
   lattato/FC), periodizzazione a blocchi.

---

## 6. Design System — "Revolut-Inspired Fintech Aesthetic"

Identità nordica, chirurgica, ad alto contrasto. I dati di carico sono un "patrimonio
energetico" da monitorare con precisione. **Mai** estetica fitness generica o template AI.

- **NO shadcn/ui, NO librerie di componenti**: solo Tailwind puro + componenti custom.
- **Token centralizzati**: definiti **solo** in `frontend/src/app/globals.css` come CSS Custom
  Properties (`--bryt-*`), mappati a utility in `frontend/tailwind.config.ts` (caricato via
  `@config`). **Vietato** usare hex/rgba direttamente nei componenti.
- Tema: dark di default (`data-theme="dark"` su `<html>`), light con `data-theme="light"`.

| Token | Utility | Dark | Light | Uso |
|-------|---------|------|-------|-----|
| canvas | `bg-canvas` | `#090A0C` | `#F6F7F9` | Sfondo app |
| surface | `bg-surface` | `#121418` | `#FFFFFF` | Card |
| elevated | `bg-elevated` | `#1C1F26` | `#EEF0F3` | Pill, bottoni |
| border | `border-line` | `rgba(255,255,255,.08)` | `rgba(9,10,12,.08)` | Bordi 1px |
| accent-pace | `*-accent-pace` | `#00E599` | | Target, efficienza aerobica |
| accent-load | `*-accent-load` | `#FF5A36` | | Stress meccanico, quadricipiti |
| accent-nutrition | `*-accent-nutrition` | `#3B82F6` | | Carbo, proteine, recupero |

Gli accenti sono **semantici**: non usarli per decorazione o fuori dal loro dominio.

- **Tipografia**: `Plus Jakarta Sans` (`font-display`, titoli, numeri) + `Inter` (`font-sans`,
  testo). Ogni dato telemetrico usa la utility `metric` (`tabular-nums`).
- **Wordmark**: `BRYT // ALPHA`, utility `wordmark` (componente `Wordmark`).
- **Layout**: Bento Grid. Raggi: `rounded-container` (= 3xl, contenitori principali),
  `rounded-card` (= 2xl, card interne), `rounded-pill` (= full, action pills).
- **Grafici Recharts**: minimalisti, niente griglie pesanti, tooltip flottanti custom,
  pillole temporali (7G/30G/90G) per la navigazione. Colori serie = token accent.

---

## 7. User Flow (App Router)

1. **`/onboarding`** — Wizard multi-step: background, PB, obiettivo, stile di vita/abitudini,
   credenziali Intervals.icu (Athlete ID + API Key). Al termine invoca il
   `TrainingPeriodizationAgent` e reindirizza a `/dashboard`.
2. **`/dashboard`** — Vista settimanale pianificato vs eseguito, sync Intervals.icu / upload
   `.fit`, modale rapida tag contestuali (asfalto, caffeina, jet lag) post-attività.
3. **`/activity/[id]`** — Grafici sovrapposti Passo/FC/Cadenza, alert divergenza cadenza del
   `MechanicalLoadAgent`, due card separate `nutrition_protocol` e `recovery_protocol`,
   feedback 👍/👎 (alpha-tester).
4. **`/plan`** — Blocchi di periodizzazione e settimane di carico/scarico.
5. **`/chat`** — Coach AI conversazionale per modifiche straordinarie al piano.

---

## 8. Processo di sviluppo

Backlog concordato con l'utente: `TODO.md` (da implementare dopo lo Step 5).


Sviluppo in 5 step sequenziali, con conferma esplicita dell'utente tra uno step e l'altro:

1. ✅ Scaffolding, Design Token & Architettura Base
2. ✅ Database Models & Schemi Pydantic (Shared State)
3. ✅ Motore deterministico di ingestione (Intervals.icu + parser `.fit`)
4. ✅ Pipeline Multi-Agent
5. ✅ Frontend completo (Revolut UI)
