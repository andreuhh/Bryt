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
```bash
docker compose up -d db                                   # Postgres locale
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload                   # API → http://localhost:8000/api/v1
.venv/bin/pytest && .venv/bin/ruff check app tests && .venv/bin/mypy app
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
| `lib/`                  | Client API, formatter (passo, durata), utility. |
| `types/`                | Tipi TS speculari agli schemi Pydantic. |

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
7. Modello LLM configurabile via `ANTHROPIC_MODEL` (default `claude-opus-5-5`).

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
- **NutritionRecoveryAgent**: unico agent con output **bipartito**:
  - `nutrition_protocol`: carboidrati, proteine per riparazione muscolare, elettroliti, timing
    caffeina rispetto all'orario di corsa.
  - `recovery_protocol`: sonno, mobilità, gestione jet lag/stress.

### Endpoint pianificati
| Metodo | Path | Step |
|--------|------|------|
| GET  | `/api/v1/health` | 1 |
| POST | `/api/v1/integrations/intervals/sync` | 3 |
| POST | `/api/v1/integrations/intervals/webhook` | 3 |
| POST | `/api/v1/activities/upload-fit` | 3 |
| POST | `/api/v1/plans/generate` | 4 |
| POST | `/api/v1/chat` | 4 |

---

## 4. Ingestione dati (costo zero)

1. **Intervals.icu (primario)**
   - Onboarding: l'utente inserisce **Athlete ID** (es. `i12345`) e **API Key** personale
     (Intervals.icu → Settings → Developer Settings).
   - Auth: **HTTP Basic**, username letterale `API_KEY`, password = chiave dell'utente.
   - `GET https://intervals.icu/api/v1/athlete/{id}/activities` per la lista;
     endpoint `/activity/{activity_id}/fit-file` per il `.fit` originale.
   - Webhook in ingresso per notifiche di nuove attività (validare il segreto condiviso).
   - Deduplicare per ID attività esterno; sync idempotente.
2. **Upload manuale `.fit` (fallback universale)**: drag & drop di file esportati da Garmin
   Connect, Coros, Strava ("Esporta originale"). Stesso parser, stessa pipeline.

Serie estratte dal `.fit`: `timestamp, pace, heart_rate, cadence, elevation, ground_contact_time`.

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
   `services/`, interpretazione nel `MechanicalLoadAgent`.
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

Sviluppo in 5 step sequenziali, con conferma esplicita dell'utente tra uno step e l'altro:

1. ✅ Scaffolding, Design Token & Architettura Base
2. Database Models & Schemi Pydantic (Shared State)
3. Motore deterministico di ingestione (Intervals.icu + parser `.fit`)
4. Pipeline Multi-Agent
5. Frontend completo (Revolut UI)
