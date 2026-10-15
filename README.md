# HistSig / HistSig

Research project assessing historical significance in software evolution.
See [CLAUDE.md](CLAUDE.md) for the full project constitution — research
scope, methodology guardrails, and development order. This README covers
only day-to-day setup.

## Status

Stages 1-3 (collection, normalization, candidate event formation) are
working end to end, plus a demo API + frontend for browsing collected
events. P/R scoring, divergence analysis, and evaluation do not exist
yet — see CLAUDE.md Section 27/28 for the full development order. The
frontend was built ahead of that stated order at the user's explicit
request (permitted under CLAUDE.md's override clause); the research
pipeline (`src/collection`, `src/processing`, `src/events`) remains fully
runnable from scripts alone, with no dependency on the API or frontend.

## Setup (research pipeline — Python)

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -r requirements.txt
cp .env.example .env          # then fill in GITHUB_TOKEN
```

## Running tests

```bash
pytest
```

Every test runs fully offline (temporary local git repos, mocked GitHub
API responses, in-memory/temp SQLite) — no network access or token is
required to run the suite.

## Running the pipeline from the CLI (no API/frontend needed)

```bash
python scripts/collect_repository.py --repo https://github.com/<owner>/<repo> --db-path data/raw/<name>.db
python scripts/normalize_repository.py --raw-db data/raw/<name>.db --processed-db data/processed/<name>.db
python scripts/form_events.py --raw-db data/raw/<name>.db --processed-db data/processed/<name>.db
```

## Running the demo API + frontend

Backend (from the project root, same venv as above):

```bash
uvicorn src.api.main:app --reload --port 8000
```

Frontend (separate terminal):

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Then open http://localhost:3000 — enter a GitHub URL to run the full
pipeline from the browser, or browse repositories already collected via
the CLI.

**Known environment quirk:** in this project's automated dev/test sandbox,
Next.js's dev-mode hot-reload (Turbopack's HMR WebSocket) failed to
handshake and silently broke client-side hydration — verified as an
environment/network issue, not an app bug, since a production build
(`npm run build && npm run start`) worked flawlessly. This has not been
reproduced outside that sandbox; `npm run dev` is expected to work
normally in a real terminal. If you hit the same symptom (pages render
but nothing is interactive, no client-side fetches ever fire), use the
production build as a workaround and/or report it.

## Project layout

```
src/collection/   # git + GitHub API collectors, raw SQLite storage       (Stage 1)
src/processing/   # identity resolution, revert detection, file renames  (Stage 2)
src/events/       # candidate historical event formation                 (Stage 3)
src/pipeline.py   # shared collect->normalize->events orchestration, used by both the CLI scripts and the API
src/api/          # FastAPI backend for the demo frontend (read-only over data/raw + data/processed)
frontend/         # Next.js demo frontend
data/raw/         # raw collected evidence, one SQLite DB per repository
data/processed/   # normalized evidence + candidate events, derived/regenerable
scripts/          # CLI entry points (collect / normalize / form_events)
tests/            # unit tests, mirrors src/ layout
config/           # explicit, versioned scoring weights/thresholds (added when Stage 4/5 needs it)
```

`src/features/`, `src/scoring/`, `src/divergence/`, `src/evaluation/`,
`src/graph/` are added when their development stage begins, not created
in advance.
