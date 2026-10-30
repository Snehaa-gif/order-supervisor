# Order Supervisor: frontend

Next.js (App Router) + Tailwind CSS operator console for the Order Supervisor backend.

```bash
cp .env.example .env.local   # optional: NEXT_PUBLIC_API_URL defaults to http://localhost:8000
npm install
npm run dev                  # http://localhost:3000
```

| Route | What it does |
| --- | --- |
| `/` | Active and completed runs, with live status and wake-up countdowns |
| `/supervisors` | Supervisor configs (built-in templates and custom ones) and a form to create one |
| `/runs/new` | Start a supervisor run for an order |
| `/runs/[id]` | Live run console: status, controls (interrupt, pause/resume, terminate), event generator and scenarios, run instructions, memory, actions outbox, timeline, final report |

The run page polls `GET /api/runs/{id}` every 2 seconds until the run closes.

Source layout: `src/lib/api.ts` (typed API client), `src/hooks/` (polling, clock, run actions), `src/components/{runs,supervisors,shell,ui}/`.
