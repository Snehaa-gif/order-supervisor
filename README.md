# Order Supervisor

A proof of concept for a **long-running AI supervisor that oversees a single order from creation to completion**,
built on Temporal.

Each order gets one Temporal workflow. Order events reach it as signals. An LLM agent wakes up when the run starts,
when an important event arrives, or at a time it scheduled for itself. On each wake-up it decides whether to act,
calls tools, updates its memory, then goes back to sleep. When the run ends it writes a final summary with
learnings and recommendations.

> **Walkthrough video:** _add link here_  ·  **Architecture note:** [ARCHITECTURE.md](ARCHITECTURE.md)

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) + Tailwind CSS |
| Backend | Python 3.12, FastAPI |
| Orchestration | Temporal Python SDK (`temporalio`) |
| Persistence | PostgreSQL (Supabase), via SQLAlchemy async |
| LLM | Google Gemini (free tier) through a small provider-neutral interface, plus an offline rule-based provider for tests |

## What it does

- **One workflow per order**, alive until the order reaches a terminal state, the agent closes it, or an operator terminates it.
- **Three inference triggers:** workflow start, an important incoming signal, and a scheduled wake-up.
- **Wake-up policy:** every event first goes through a lightweight deterministic classifier. Critical, terminal and unknown events wake the agent; routine ones wait for the next scheduled check. The agent can tune this per run (`set_wake_guidance`).
- **Tools:** 4 simulated action tools (send customer message, create internal note, escalate issue, mark for review), all idempotent, plus 4 control tools (schedule next wake, update memory, set wake guidance, close workflow).
- **Memory and timeline:** a full timeline in Postgres, a compact memory summary that the agent rewrites, and automatic LLM compaction of older history.
- **Human in the loop:** add run-specific instructions to a live run (optionally waking the agent), interrupt, pause, resume and terminate.
- **End-of-run report:** summary, outcome, key actions, learnings and recommendations.
- **Good-to-haves included:** agent-generated wake guidance, escalation of unknown events, `continue_as_new` for long histories, LLM memory compaction, 3 supervisor templates plus custom ones, and model fallback when the free tier is busy or out of quota.

## Run it locally

**Prerequisites:**
- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you)
- Node.js 20+
- the [Temporal CLI](https://docs.temporal.io/cli#install): `brew install temporal` or `curl -sSf https://temporal.download/cli.sh | sh`

**1. Configure**

```bash
cp backend/.env.example backend/.env
# Set GEMINI_API_KEY (free from https://aistudio.google.com) and DATABASE_URL.
# DATABASE_URL: a Supabase "Session pooler" URI works as-is. Leave it unset to use a local SQLite file.
# No API key? Set LLM_PROVIDER=mock to run the whole system offline.
cp frontend/.env.example frontend/.env.local
make install
```

**2. Start the four processes**, each in its own terminal:

```bash
make temporal   # Temporal dev server   -> UI at http://localhost:8233
make worker     # Temporal worker (workflow + activities)
make api        # FastAPI               -> http://localhost:8000/docs
make web        # Next.js UI            -> http://localhost:3000
```

Tables and the three supervisor templates are created automatically when the API starts.

**3. Try it**

1. Open http://localhost:3000. Under **Supervisors**, create one (for a quick demo, set *max sleep* to 1–2 minutes).
2. Click **Start a run**, pick that supervisor, and start an order.
3. On the run page, send events or play a scenario. Watch the agent wake, act, update its memory and go back to sleep.
4. Add an instruction, then pause, resume, interrupt or terminate the run, and read the final report.

You can also drive it from the terminal:

```bash
cd backend
uv run python scripts/simulate.py start --order ORD-1001
uv run python scripts/simulate.py scenario <run_id> rough_delivery --delay 10
uv run python scripts/simulate.py event <run_id> refund_requested --payload '{"reason": "damaged"}'
uv run python scripts/simulate.py watch <run_id>
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta` | Tools, event types, wake levels (for the UI) |
| GET / POST | `/api/supervisors` | List / create supervisor configs |
| GET | `/api/supervisors/{id}` | One supervisor |
| POST | `/api/runs` | Start a run (starts the order's workflow) |
| GET | `/api/runs?active=true\|false` | List runs |
| GET | `/api/runs/{run_id}` | Run state, timeline, tool executions, final report |
| POST | `/api/runs/{run_id}/events` | Send an order event (signal) |
| POST | `/api/runs/{run_id}/instructions` | Add a run-specific instruction |
| POST | `/api/runs/{run_id}/interrupt` | Wake the agent now |
| POST | `/api/runs/{run_id}/pause` · `/resume` | Pause / resume the agent |
| POST | `/api/runs/{run_id}/terminate` | Close the run; it still writes its final report |

Interactive docs: http://localhost:8000/docs

## Tests

```bash
make test   # 59 tests: unit, API, Gemini adapter, and full workflow runs on Temporal's time-skipping test server
make lint
```

The workflow tests run the real workflow and activities against an in-process Temporal test server with a
rule-based LLM. They cover the full lifecycle, scheduled wake-ups, pause/resume, instructions, interrupts,
unknown-event escalation, continue-as-new, LLM outages and tool idempotency.

## Project layout

```
backend/
  app/
    domain.py                 shared, immutable models (events, config, state, timeline)
    workflows/
      order_supervisor.py     the long-running workflow (signals, sleep/wake loop, agent turn)
      activities.py           LLM step, tool execution, persistence, compaction, final report
    agent/
      classifier.py           wake-up policy
      tools.py                tool catalogue and validation
      prompts.py              prompt builders
      llm/                    Gemini adapter, mock provider, interface
    api/                      FastAPI routes, schemas, Temporal gateway
    db/                       SQLAlchemy models, session, repository
    worker.py · main.py · templates.py
  scripts/simulate.py         event generator
  tests/
frontend/src/
  app/                        pages: runs, supervisors, new run, run detail
  components/                 runs/, supervisors/, ui/, shell/
  lib/api.ts                  typed API client
```
