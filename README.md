# Digital Ghost / HistSig

Research project assessing historical significance in software evolution.
See [CLAUDE.md](CLAUDE.md) for the full project constitution — research
scope, methodology guardrails, and development order. This README covers
only day-to-day setup.

## Status

Stage 1 (repository collection) is in progress. No scoring, graph, API, or
frontend exists yet — see CLAUDE.md Section 27/28 for the development order.

## Setup

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

Collection tests run fully offline (against temporary local git repos and
mocked GitHub API responses) — no network access or token is required to
run the test suite.

## Project layout

```
src/collection/   # git + GitHub API collectors, raw SQLite storage
data/raw/         # raw collected evidence, one SQLite DB per repository
scripts/          # CLI entry points
tests/            # unit tests, mirrors src/ layout
config/           # explicit, versioned scoring weights/thresholds
```

Other `src/` modules (`processing/`, `events/`, `features/`, `scoring/`,
`divergence/`, `evaluation/`, `graph/`, `api/`) are added when their
development stage begins, not created in advance.
