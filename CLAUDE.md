# CLAUDE.md — HistSig / HistSig Project Constitution

This file is the long-term governing document for this repository. It applies to
every future Claude Code session working here. When instructions elsewhere
conflict with this file, this file wins unless the user explicitly overrides it
in the conversation.

This is a **research project first**, with a demonstration application built
around it. Read Section 5 and Section 31 before doing anything else — they
define the priority order that governs every other decision in this document.

---

## 1. Project Identity

- **Project name:** HistSig
- **Research framework:** HistSig
- **Research topic:** "Assessing Historical Significance in Software Evolution:
  A Feature-Based Ranking Framework for Identifying Pivotal Repository Events"
- **Domain:** Mining Software Repositories (MSR), Software Evolution, Software
  Archaeology, Repository Mining, Software Engineering Analytics, Knowledge
  Graphs, Historical Analysis of Software Systems.

---

## 2. Core Project Idea

Software repositories contain thousands of commits, files, issues, pull
requests, reviews, comments, releases, contributors, and tags — but repository
interfaces present all of this chronologically, with no notion of importance.

**Central research problem:** How can we automatically identify which
repository events were historically significant, instead of treating every
commit or artifact as equally important?

HistSig answers this with a feature-based ranking framework for repository
events, built on two deliberately separate axes:

### Perceived Significance (P)
Evidence that an event attracted attention or appeared important around the
time it occurred. Candidate signals: discussion depth, comments, reviewers,
review intensity, code churn, number of affected files, release proximity,
issue severity/labels where available.

### Historical Salience (R)
Evidence that an event continued to matter after it occurred. Candidate
signals: later references, file survival, module survival, subsequent
modifications, repeated maintenance, re-review activity, presence across later
releases.

**P and R must remain conceptually separate.** Do not collapse them into a
single score early on. The research specifically studies the relationship and
divergence between P and R — collapsing them would erase the thing being
studied.

---

## 3. Four Historical Significance Categories

HistSig supports analysis across four conceptual quadrants. These are
**research concepts to be empirically tested, not established ground truth.**

| Quadrant | Label | Meaning |
|---|---|---|
| High P / High R | "Truly Important" | Substantial attention at the time, and long-term salience. |
| High P / Low R | "Discussed but Forgotten" | Substantial immediate attention, limited long-term salience. |
| Low P / High R | "Silent but Critical" | Limited immediate attention, became important later. |
| Low P / Low R | "Routine Noise" | Limited attention and limited lasting significance. |

The empirical evaluation must determine whether these categories are
actually meaningful — do not assume they are and build as if proven.

---

## 4. Core Research Pipeline

```
Data Collection → Feature Extraction → Scoring → Divergence Analysis
→ Evaluation → Knowledge Graph → Paper Writing
```

Each stage has one clear responsibility. Do not blur stages together.

### Phase 1 — Data Collection
Input: a GitHub repository URL.

Collect: Git history, commits, commit authors, timestamps, commit messages,
changed files, code churn, issues, issue comments, pull requests, PR reviews,
PR comments, releases, tags, labels, contributors.

Technologies: Git, PyDriller, GitHub REST API, GitHub GraphQL API where useful.

Storage: SQLite initially. **Preserve raw evidence wherever practical** —
raw data is the foundation for provenance (see Section 24) and must not be
lossily transformed on ingest.

### Phase 2 — Feature Extraction
Transform repository artifacts into structured **candidate historical
events**, then extract P features and R features from them.

Feature extraction must be **deterministic and reproducible**. Do not use an
LLM to generate core features unless explicitly justified later as a
separate, clearly labeled experiment.

### Phase 3 — HistSig Scoring
Compute `P(event)` and `R(event)` from explicitly defined features. Generic
form:

```
P(e) = Σ wi × pi(e)
R(e) = Σ vj × rj(e)
```

Feature weights must remain **configurable**, never silently hard-coded.
Possible future weighting strategies (equal, expert-informed, learned,
optimized) are research decisions — do not choose one automatically. See
Section 25.

---

## 5. Research-First Principle

**The most important component of this project is the HistSig research
methodology and its empirical validation.** HistSig is the
demonstration platform built around that research — not the other way around.

**Do:**
- Prioritize reproducibility
- Preserve raw evidence
- Make algorithms transparent
- Keep feature definitions explicit
- Build experiments, baselines, and evaluation scripts
- Record assumptions
- Maintain research documentation
- Make results reproducible

**Do not:**
- Optimize UI before the algorithm works
- Add unnecessary AI agents
- Introduce unnecessary frameworks
- Hide methodology inside application code
- Treat an LLM's opinion as ground truth
- Claim novelty simply because Neo4j is used
- Claim novelty simply because GitHub data is mined
- Claim novelty simply because an LLM is involved

---

## 6. Research Boundary — What Is NOT Automatically Novel

The following are established techniques or infrastructure, not research
contributions in themselves: GitHub mining, Git mining, PyDriller, repository
analytics, software evolution analysis, knowledge graphs, Neo4j, graph
visualization, LLM summarization, repository question answering, contributor
analysis.

**The actual potential research contribution is:** HistSig's explicit
formulation of repository-event historical significance ranking, the P/R
separation, divergence analysis, and empirical validation against human
judgment and baselines.

Never claim novelty for the supporting infrastructure. Always be precise
about what is and isn't the contribution when writing docs, comments, or the
paper itself.

---

## 7. Knowledge Graph Role

Neo4j is part of the HistSig architecture, representing relationships
between entities such as: `Developer`, `Commit`, `File`, `Issue`,
`PullRequest`, `Review`, `Release`, `Module`, `HistoricalEvent`.

Possible relationship types: `AUTHORED`, `MODIFIES`, `FIXES`, `REFERENCES`,
`REVIEWED_BY`, `DISCUSSED_IN`, `INCLUDED_IN`, `AFFECTS`, `RELATED_TO`.

The graph should support traversals such as:

```
Developer → Commit → File → Issue → PullRequest → Release
HistoricalEvent → Related Commit → Modified File → Related Issue
                → Related PR → Later Modification
```

**The knowledge graph is an evidence and relationship layer. It is not the
core research novelty** (see Section 6). Do not over-engineer the ontology
initially — start minimal and extend only when a concrete query need arises.

---

## 8. HistSig Role

HistSig is the platform that demonstrates HistSig. Eventually it should
let a user:

1. Enter a repository URL
2. Analyze the repository
3. Collect repository evidence
4. Construct the knowledge graph
5. Generate candidate historical events
6. Calculate P and R
7. Rank events
8. Identify divergence categories
9. Explore historical milestones
10. Inspect evidence behind a ranking
11. Ask questions about repository history
12. Optionally receive evidence-grounded natural-language explanations

**The application must never obscure the research methodology.** The research
engine must remain independently executable without the frontend — it should
be possible to run the full HistSig pipeline from a script or notebook with
no UI involved.

---

## 9. Optional LLM Role

An LLM may eventually be used for: historical summaries, repository
explanations, evidence-based question answering, narrative reconstruction.

**Example flow.** User asks: "Why was this authentication file changed?"
The system first retrieves evidence (`Issue → PullRequest → Commit → File →
Later changes`), then gives that evidence to the LLM to summarize.

Rules:
- The LLM must **not** invent historical intent.
- The LLM must **not** be treated as ground truth.
- The LLM must **not** determine whether HistSig is correct.
- HistSig must remain independently testable without any LLM in the loop.

---

## 10. Evidence-First Principle

Every historical explanation the system produces must be traceable back to
repository evidence.

**Prefer:** `Repository evidence → Structured representation → Knowledge
graph → Evidence retrieval → Explanation`

**Avoid:** `Repository → LLM → Unverified story`

Any future LLM implementation must explicitly distinguish: documented
evidence, derived evidence, inference, uncertainty, and unavailable
information. Do not let these categories blur together in generated text.

---

## 11. Evaluation Is Critical

HistSig cannot claim to work merely because its rankings "look reasonable."

**Human validation (target):** 5–8 repositories, approximately 300–500
labelled events if feasible. Human annotators judge historical significance
using a fixed rubric. Measure inter-rater agreement where possible.

**Baselines (candidates):** chronology-only, code-churn-only,
discussion-only, release-only, equal-weight feature score.

**Metrics (candidates):** Spearman rank correlation, Precision@K, nDCG,
inter-rater agreement, ablation analysis, sensitivity analysis.

The exact experimental design must be discussed and approved before
implementation — do not lock in an evaluation design unilaterally.

---

## 12. Research Questions

- **RQ1:** How strongly do perceived significance and historical salience
  rankings correlate?
- **RQ2:** What characteristics distinguish High-P/Low-R repository events?
- **RQ3:** What characteristics distinguish Low-P/High-R repository events?
- **RQ4:** Does HistSig outperform simple baseline approaches when ranking
  human-judged historically significant events?
- **RQ5:** Which feature groups contribute most strongly to HistSig
  performance?

These may evolve as the literature review and pilot experiments progress,
but **must not be changed silently** — any change is flagged to the user
(see Section 25).

---

## 13. Reproducibility Requirements

Every experiment must document: repository, repository version/commit,
collection date, extraction configuration, feature definitions, normalization
method, scoring weights, thresholds, random seeds where applicable,
evaluation dataset, evaluation methodology, software version, Python
dependencies.

Avoid undocumented manual processing. Research results should be generated
through scripts whenever practical, not one-off manual steps.

---

## 14. Data Management

```
data/
├── raw/          # never silently overwritten
├── processed/    # derived from raw, regenerable
└── results/      # experimental outputs, kept separate
```

Do not commit large repository clones or unnecessary generated data into Git.
Use `.gitignore` appropriately.

---

## 15. Expected Initial Project Structure

A clean structure to converge toward (refine as implementation begins — do
not create folders merely for appearance):

```
src/
├── collection/
├── processing/
├── events/
├── features/
├── scoring/
├── divergence/
├── evaluation/
└── graph/

data/
├── raw/
├── processed/
└── results/

tests/
notebooks/
docs/
scripts/
```

---

## 16. Technology Principles

| Concern | Choice |
|---|---|
| Language | Python |
| Repository mining | Git, PyDriller |
| GitHub data | GitHub REST API; GraphQL API where justified |
| Initial storage | SQLite |
| Optional scalable relational storage | PostgreSQL |
| Knowledge graph | Neo4j, Cypher |
| Data processing | Pandas, NumPy |
| Statistical analysis | SciPy; scikit-learn / statsmodels where appropriate |
| Backend | FastAPI |
| Frontend | Next.js / TypeScript |
| Graph visualization | Cytoscape.js or D3.js |
| LLM | Optional — never a mandatory dependency for the core HistSig experiment |

---

## 17. Coding Principles

1. Prefer simple solutions.
2. Avoid unnecessary abstractions.
3. Use clear function and variable names.
4. Keep research logic separate from UI logic.
5. Keep data collection separate from analysis.
6. Keep scoring functions independently testable.
7. Write tests for important research calculations.
8. Do not hide constants.
9. Make configuration explicit.
10. Preserve reproducibility.
11. Avoid premature optimization.
12. Do not introduce dependencies without a reason.
13. Document non-obvious research decisions.
14. Prefer deterministic behavior.
15. Handle missing repository data explicitly.

---

## 18. Git Practices

Use meaningful, conventional commit messages, e.g.:

```
feat: add GitHub issue collector
feat: implement commit mining
feat: add P feature extraction
feat: add R feature extraction
feat: implement HistSig scoring
test: add scoring validation
feat: add Neo4j event ingestion
docs: document event formation
```

Do not create meaningless commits such as "update", "changes", "stuff",
"final".

---

## 19. Testing Principles

Testing matters especially here because this is research software whose
outputs feed a paper's claims. Eventually test: API collection, commit
extraction, issue extraction, PR extraction, event formation, feature
normalization, P scoring, R scoring, divergence classification, graph
insertion, graph queries, evaluation metrics.

**The HistSig scoring implementation must have deterministic unit tests:**
given a fixed event and fixed feature values, the same input must always
produce the same score.

---

## 20. Handling Missing Data

Repositories are inconsistent — some may have no issues, no PR reviews,
limited release history, shallow Git history, missing contributor metadata,
deleted files, or incomplete issue/PR links.

**Never silently treat missing information as zero without documenting why.**
Distinguish explicitly between: true zero, unavailable, not applicable, and
missing. Feature design must address this distinction directly, not paper
over it with defaults.

---

## 21. Large Repositories

Support for large repositories comes later. **Correctness comes before
scale.** Build the correct research pipeline first, profile performance,
then optimize bottlenecks. Future techniques may include incremental mining,
caching, batching, pagination, parallel processing, database indexing, and
sampling for experiments — none of these should be introduced preemptively.

---

## 22. Security

Never hard-code: GitHub tokens, API keys, passwords, database credentials,
LLM API keys. Use environment variables, e.g. `GITHUB_TOKEN`, `NEO4J_URI`,
`NEO4J_USERNAME`, `NEO4J_PASSWORD`, `OPENAI_API_KEY` (or equivalent provider
variables). Never commit `.env`; provide `.env.example`.

---

## 23. API Usage

GitHub API calls must account for authentication, rate limits, pagination,
retries, transient errors, and missing data. Cache collected information
when appropriate — do not repeatedly request the same data unnecessarily.
The collection layer should be designed so analysis can run later without
repeatedly hitting GitHub.

---

## 24. Research Data Provenance

Every derived feature must eventually be traceable to its source artifacts.
For example:

```
P discussion score  ← PR #121 ← 35 comments ← 4 reviewers
R file-survival score ← login.py ← exists across releases v1.0–v4.0
```

This provenance is essential — the system must be able to answer "why did
HistSig give this event a high score?" with the underlying evidence, not
just a number.

---

## 25. What Claude Code Must Not Do Without Approval

Do not independently:

- Change the research questions
- Redefine P
- Redefine R
- Invent new significance categories
- Change the scoring formula
- Choose arbitrary weights
- Claim statistical significance without testing
- Claim novelty
- Add an LLM dependency
- Replace Neo4j with another database
- Introduce an ontology
- Add multi-agent architecture
- Add GitLab/Bitbucket/Azure DevOps support
- Build a production-grade frontend
- Redesign the entire architecture

**If a change affects the research methodology, explain the issue and ask
for approval before implementing it.**

---

## 26. Decision-Making Rule

When uncertain between:

- **A.** a simple implementation that preserves research transparency, or
- **B.** a complex implementation with additional functionality,

**prefer A.**

This project is: Research-first → Evidence-first → Reproducible →
Explainable → Modular → Simple before sophisticated.

---

## 27. Development Order

1. Project structure
2. Repository collection
3. Raw data storage
4. Data normalization
5. Candidate event formation
6. P feature extraction
7. R feature extraction
8. HistSig scoring
9. Divergence analysis
10. Evaluation framework
11. Baselines
12. Human annotation support
13. Neo4j graph
14. Graph queries
15. Temporal visualization
16. Backend API
17. Frontend
18. Optional LLM explanation layer

**Do not reverse this order merely because frontend features are more
visually impressive.**

---

## 28. First Development Milestone

The first implementation milestone is **not** the complete application. In
order:

1. Given a public GitHub repository, successfully collect and store enough
   repository evidence to support later HistSig feature extraction.
2. Convert repository evidence into candidate historical events.
3. Extract P and R features.
4. Implement and test HistSig scoring.
5. Evaluate HistSig.

Only after the research core works should the complete HistSig
experience be built.

---

## 29. Claude's Role

Acting as a senior software engineer and research engineering assistant,
responsibilities include: writing clean code, identifying implementation
problems, finding bugs, writing tests, explaining technical decisions,
maintaining project structure, implementing approved methodology, improving
reproducibility, and helping with data processing, Neo4j, and experiments.

**Claude is not the researcher making final methodological decisions.** When
a decision could materially change the research contribution, stop and
explain the options before implementing it.

---

## 30. Response Behavior

Before implementing a significant feature:

1. Explain what you understood.
2. Identify relevant existing files.
3. Explain the proposed approach.
4. Identify research implications.
5. Identify potential risks.
6. Ask for approval if the decision affects methodology.

For small, unambiguous implementation tasks, proceed normally — do not
repeatedly ask for approval for trivial code changes.

---

## 31. Important Distinction

Always keep separate:

**Research contribution (HistSig):** feature-based historical event ranking,
P/R separation, divergence analysis, empirical validation.

**Supporting infrastructure (HistSig):** repository collection,
storage, Neo4j, graph visualization, dashboard, evidence retrieval, optional
LLM.

This distinction must remain clear throughout the project — in code
organization, in documentation, and in how the paper describes contributions.

---

## 32. Final Rule

Before adding any feature, ask:

> Does this directly help us answer our research questions, improve
> reproducibility, support evidence retrieval, or demonstrate the research
> contribution?

- **If NO:** do not add it automatically.
- **If MAYBE:** explain why it might be useful, and let the user decide.
- **If YES:** implement it in the simplest maintainable way.

---

# Addendum: Living Project State

Everything above this line is the fixed constitution, written before
implementation began. Everything below is a living record of where the
project actually stands — updated as work progresses, so a new session
(or one resuming after context compaction) doesn't have to re-derive it
from git history or a lost conversation. Sections 1-32 still govern; this
addendum records facts and decisions, not new rules.

## 33. Implementation Status

- **Phase 1 (Data Collection): done.** `src/collection/` — Git history via
  PyDriller, issues/PRs/reviews/releases via GitHub GraphQL. Validated
  against two real repositories (`pallets/click`, `pallets/markupsafe`),
  re-collected several times as bugs were found and fixed (see Section 35).
- **Phase 2 (Feature Extraction) — event formation: done.**
  `src/events/` — candidate historical events, two granularities generated
  and kept side by side (see Section 34).
- **Phase 2 — normalization prerequisite: done.** `src/processing/` —
  contributor identity resolution (git identity ↔ GitHub login), revert
  detection, file-rename/identity tracking across renames. Needed before
  event formation and before R features (file survival) can work.
- **Phase 2 — P feature extraction: done.** `src/features/`. All ten P
  features implemented, unit-tested, and verified against real data with
  hand-computed worked examples (each matched exactly) plus repo-wide
  invariant checks (e.g. `distinct_commenters ≤ comment_count`,
  `review_rounds ≥ reviewer_count`, no negative `churn`/`files_changed`/
  `reaction_count`, status/value null-consistency): `comment_count`,
  `distinct_commenters`, `reviewer_count`, `review_rounds`, `files_changed`,
  `churn`, `issue_link_present`, `issue_has_label`, `release_proximity`,
  `reaction_count`. Four of these needed a real methodology decision (or a
  real-data check first) before they could be built — see the new bullets
  in Section 34. `reaction_count` (GitHub emoji reactions on the PR itself)
  was the last one added, specifically because it's a genuinely new
  attention signal — someone can react without commenting — not redundant
  with the discussion-based features above it.
- **Phase 2 — R feature extraction: done.** `src/features/r_features.py`,
  `event_r_features` table (kept structurally separate from
  `event_p_features` — see Section 34). Five built, all unit-tested and
  verified against real data with hand-computed worked examples:
  `maturity` (event-level context every R feature needs, not a weighted
  feature itself — see Section 34), `files_survived` (uses Stage 2's
  `file_identities`/`file_path_history`, built back then specifically for
  this), `subsequent_modification_count` (repeated maintenance — how many
  later commits touched the same file(s) again), `releases_since_count`
  (presence across later releases — how many releases shipped after this
  event; needs `raw_conn` for the `releases` table), and
  `later_references_count` (how many other issues/PRs referenced this PR
  after it concluded, from GitHub's own `crossReferencedEvent` timeline
  data — a new Stage 1 table, `pr_cross_references`; needs `raw_conn`,
  PR-only). Real-data verification caught and fixed four issues before
  calling the set done — two correctness bugs, one real performance
  stall (`subsequent_modification_count` took minutes on pallets/click
  before a precomputed-index fast path fixed it), and one GitHub GraphQL
  API quirk (`timelineItems.totalCount` ignores its own `itemTypes`
  filter) — see Section 34's R bullets; all four are worth reading before
  adding another R feature, since they're the kind of mistake that's easy
  to repeat. `re-review_activity` (the sixth CLAUDE.md Section 2 R
  candidate) was checked against real data and explicitly **not built** —
  see Section 34.
- **Phase 3 (HistSig Scoring) — both P-score and R-score done, still not
  combined.** `src/scoring/` — `src/scoring/ranking.py` holds the shared
  algorithm (percentile-rank average per `(granularity, event_type)`
  group, equal-weighted, plus a configurable top-percentile threshold);
  `p_score.py` and `r_score.py` are thin wrappers naming each axis's own
  feature table/list. R-score deliberately excludes `maturity` from the
  averaged features — it's context, not a weighted signal, per Section
  34 — which was built and documented, not asked about again, since it
  followed directly from R's already-settled design. Every methodology
  choice in the scoring algorithm itself (normalization method,
  per-event-type grouping, the threshold rule) was discussed and approved
  by the user before implementing for P, then explicitly reused for R at
  the user's request ("do everything we did for P" for R) — see Section
  34. This is **still not** the full HistSig score: P and R are scored
  independently and nothing here combines them into one number — that's
  divergence analysis, not started. Wired into the demo app: `GET
  .../events` accepts `high_p` and `high_r` (independently, combinable)
  and returns per-group `p_thresholds`/`r_thresholds`; `GET
  .../events/{id}` returns both `p_score` and `r_score`; the frontend
  shows "high P"/"high R" badges, both raw scores, independent "P
  attention"/"R attention" filters, and (when filtering by attention with
  no specific event_type picked) splits results into one section per
  event_type so each group's own threshold is visible side by side for
  both axes at once.
  R-score also excludes events below `MIN_MATURITY_FOR_SCORING` (default
  0.05, `--min-maturity` on `scripts/compute_r_scores.py`) from the
  ranking population entirely — see Section 34's new bullet for why and
  how this was decided; the frontend shows "too young to rank yet" for
  such an event instead of a score, while still showing its raw R feature
  values (nothing about raw evidence is hidden, only the ranking).
- **Phase 4 (Divergence Analysis) — first pass done and now visible in
  the demo app's UI.** `src/divergence/` — `classify_divergence` labels
  every event that has *both* a non-null `is_high_p` and `is_high_r`
  (i.e. both axes actually got scored) into one of Section 3's four
  quadrants, reusing the already-approved `is_high_p`/`is_high_r` flags
  directly — no new threshold or category invented (Section 25). An
  event missing either axis is left unclassified rather than guessed at,
  same missing-data principle as everywhere else. Stored in
  `event_divergence` (`scripts/compute_divergence.py`, requires P and R
  scores to already exist — and always runs as part of `run_full_pipeline`,
  see below). Run against all three real repos as a first empirical look
  (not yet a validated finding — Section 11's evaluation stage is what
  would check this against human judgment):
  | repo | classified | Truly Important | Discussed but Forgotten | Silent but Critical | Routine Noise |
  |---|---|---|---|---|---|
  | markupsafe | 1646 | 58 | 106 | 107 | 1375 |
  | click | 5733 | 263 | 348 | 310 | 4812 |
  | venvdoctor | 14 | 0 | 2 | 2 | 10 |
  Both real repos populate "Silent but Critical" non-trivially (107 and
  310 events) — the quadrant RQ3 cares about isn't empty, which is a
  necessary (not sufficient) condition for the framework being useful.
  venvdoctor is too small (14 classified events) to read anything into
  its counts. Frontend: `GET .../events` accepts a `quadrant` filter (and
  `GET .../divergence?granularity=...` returns the 4-way count summary);
  the events list page shows a "Divergence" panel — four clickable cards
  (count + description per quadrant, from `QUADRANT_LABELS`/
  `QUADRANT_DESCRIPTIONS` in `frontend/app/lib/api.ts`) that both display
  the repo's quadrant distribution at a glance and act as a quick filter;
  event rows and the event detail page show a quadrant badge (reusing
  `Badge`'s tone system — green for Truly Important, amber for Discussed
  but Forgotten matching P's own color, violet for Silent but Critical
  matching R's own color, neutral gray for Routine Noise) plus a one-line
  description of what that quadrant means.
- **P/R concentration heatmap added to the events list page** — a finer
  view of RQ1 ("how strongly do perceived significance and historical
  salience correlate?") than the 4-quadrant split above: every event with
  both scores computed is binned into a 10x10 grid over `[0,1] x [0,1]`
  (`src/api/repositories.py: get_pr_heatmap`, `GET .../pr-heatmap`), and
  the frontend renders it as a genuine heatmap — sequential single-hue
  (blue, light->dark, the design system's documented sequential ramp —
  see the `dataviz` skill) on a log scale (`log1p(count)`, since a few
  cells otherwise dwarf the rest — markupsafe's own distribution runs
  from 0 to 64 in a single cell), a hover readout giving the exact P/R
  range and count per cell, a light->dark legend, and a "Show as table"
  toggle exposing the same grid as plain numbers (the skill's
  accessibility-pass requirement: a table view must exist alongside every
  chart). Purely a read/aggregation of already-computed P/R scores —
  introduces no new scoring methodology, same as divergence classification.
- **Real code-diff viewer added to the event detail page — evidence
  inspection with no LLM involved, per CLAUDE.md Section 8/10's
  "inspect evidence behind a ranking" / Evidence-First Principle.**
  `src/collection/git_collector.py: get_commit_diff(clone_dir, commit_hash)`
  runs `git show --no-color --format= <hash>` directly against the local
  clone `ensure_local_clone` already keeps under `data/raw/_clones/` —
  deliberately a read-on-demand path, not a Stage 1 collection step or a
  new database column: diffs can be large and most are never looked at,
  so nothing is stored, the clone is regenerated evidence enough
  (Section 21: correctness/simplicity before scale). Returns `None` when
  the clone directory is missing; truncates very large diffs and reports
  `truncated` rather than silently cutting one off. `src/api/repositories.py:
  get_commit_diff(safe_name, commit_hash)` validates the hash against a
  plain hex pattern *before* it ever reaches a subprocess call (rules out
  a crafted value like `--upload-pack=...` being read as a git option)
  and confirms the hash is actually one of this repository's own
  collected commits before shelling out at all. New endpoint: `GET
  .../commits/{commit_hash}/diff`. Frontend: each commit in the event
  detail page's commit list that was found locally (the same check
  already used for "not in collected history" there) gets a "View diff"
  toggle that fetches the diff on click and renders it with basic +/-/hunk
  coloring in a scrollable monospace block — real code, not a summary,
  and nothing about it depends on or ever calls an LLM.
- **First and only LLM integration in the codebase so far: an optional
  "explain this diff" feature, exactly the flow CLAUDE.md Section 9
  already anticipated** (`Repository evidence -> Explanation`, evidence
  retrieved first, then handed to the LLM to summarize — never
  `Repository -> LLM -> Unverified story`, Section 10). Scope
  deliberately narrow: explaining one already-real diff, nothing about
  scoring, ranking, or divergence classification. `src/llm/groq_client.py:
  explain_diff(commit_message, diff_text)` calls Groq's free-tier,
  OpenAI-compatible chat completions API (`GROQ_API_KEY`, default model
  `openai/gpt-oss-120b`, both from `.env.example`) — Groq was picked over
  Gemini and a fully local Ollama setup explicitly by the user when
  offered the choice (fast, generous free tier, no local hardware
  dependency), not chosen unilaterally (Section 25: adding an LLM
  dependency needs approval). The default model went through one real
  fix after first real-key testing: the original default
  (`llama-3.3-70b-versatile`) had been retired from Groq's free tier and
  404ed with `model_not_found`; the live `GET
  https://api.groq.com/openai/v1/models` list was checked rather than
  guessed at a replacement, and `openai/gpt-oss-120b` was picked from
  what was actually still available. That model is also a *reasoning*
  model — it spends part of its `max_tokens` budget on a hidden
  reasoning trace before the visible answer, unlike a plain chat model —
  which silently produced empty explanations (`finish_reason: "length"`,
  empty `message.content`) at this module's original `max_tokens: 300`;
  raised to 600 after confirming against a real request that finish
  reason came back `"stop"` (a complete answer) at that budget. **Lesson
  for next time a Groq model is swapped in: verify both model
  availability and `max_tokens` sufficiency against a real request before
  trusting a default, the same real-data-first discipline this project
  already applies to P/R feature thresholds — a "the API accepted the
  request" 200 status is not the same as "the response actually contains
  the answer."** The system prompt is the actual Section 10
  enforcement point: the model is given only the real commit message and
  real diff already shown elsewhere in the UI and is explicitly told not
  to invent motivation, issue numbers, or context beyond that evidence,
  and to say so plainly when the diff alone doesn't make the reason for
  a change clear. `src/api/repositories.py: explain_commit_diff` reuses
  `get_commit_diff` for the evidence and is purely additive — every
  collection/normalization/feature/scoring/divergence path in the
  codebase is fully testable and runnable with `GROQ_API_KEY` unset
  (Section 9's "HistSig must remain independently testable without any
  LLM in the loop"), verified by the existing test suite never setting
  that variable. New endpoint: `POST .../commits/{hash}/explain`.
  Frontend: an "Explain this diff (AI, optional)" link appears once a
  diff is expanded; the result renders in a visually distinct panel
  labeled "AI explanation — generated from the diff above, not verified
  evidence" (Section 10: documented evidence, derived evidence, and
  AI-derived inference must never blur together) rather than looking
  like part of the collected evidence itself.
- **`src/pipeline.py: run_full_pipeline` now runs the complete research
  chain by default for any repository, not just collection.**
  `DEFAULT_STAGES` grew from `("collect", "normalize", "events")` to
  also include `p_features`, `r_features`, `p_scores`, `r_scores`,
  `divergence` — so the demo app's one-click "Analyze repository" flow
  (`src/api/jobs.py`), and any future caller that doesn't override
  `stages`, now takes a repo all the way to a full P/R score and
  divergence classification, not just candidate events. Before this,
  only whichever repos happened to have `scripts/extract_features.py`
  etc. run against them by hand (in practice, only `pallets/click`) had
  P data at all — this was a real, user-visible bug: `GET .../events`
  crashed with a 500 whenever `high_p` was requested against a repo
  missing `event_p_scores` (see the bullet below). Every new stage is
  pure orchestration reusing the exact functions `scripts/*.py` already
  call and that are already unit-tested elsewhere — `pipeline.py` adds no
  new methodology of its own. `scripts/collect_repository.py` is
  unaffected (it explicitly passes `stages=("collect",)`).
- **Two real "safe to re-run" bugs found and fixed while wiring the
  above** — both would have crashed "Analyze repository" a second time
  against any repo that already had processed data (a completely normal
  usage pattern: re-analyzing to pick up new commits), not just a
  hypothetical:
  1. `insert_contributors` (`src/processing/storage.py`) deleted
     `contributors` before clearing `commit_annotations`, whose
     `contributor_id` column references it — a second `normalize` run
     against the same repo raised `sqlite3.IntegrityError`. Fixed by
     clearing `commit_annotations` first (that table gets fully
     re-populated later in the same function anyway, so this is free,
     not a duplicated responsibility).
  2. `insert_events` (`src/events/storage.py`) deleted `candidate_events`
     while `event_commits` and every later stage's per-event table
     (`event_p_features`, `event_r_features`, `event_p_scores`,
     `event_r_scores`, `event_divergence`) still referenced those event
     ids — same class of bug, one stage later, newly surfaced by this
     session's P/R/divergence tables. Fixed at the schema level instead
     of patching `insert_events` to know about every downstream table
     (which would blur Section 4's "keep stages separate" the other
     way): every one of those tables' `event_id` FK now declares
     `ON DELETE CASCADE` against `candidate_events(id)`, so deleting a
     repo's events alone correctly wipes its whole downstream analysis.
     Since every one of those tables is already fully dropped and
     recreated by its own `reset_schema` on every extraction/scoring/
     divergence run, this schema change needed no live migration for
     fresh runs — but the three real repos' *existing* processed
     `.db` files predated the cascade and had to be deleted and rebuilt
     from scratch once (same accepted procedure as every other raw/
     processed schema change this project has hit — see Section 35),
     which also served as the first real end-to-end verification of the
     new full-pipeline chain.
  **Lesson worth generalizing: any table added with `event_id ...
  REFERENCES candidate_events(id)` (or any other FK into a table an
  earlier stage might legitimately re-run and rewrite) must declare
  `ON DELETE CASCADE` from the start** — this class of bug was hit twice
  in immediate succession specifically because it wasn't.
- **Demo application** (`src/api/` FastAPI backend + `frontend/` Next.js
  app): built ahead of the Section 27 development order, at the user's
  explicit request after being shown the conflict with Section 27/Section
  25's "no production-grade frontend without approval" rule — permitted
  under this file's own override clause ("this file wins unless the user
  explicitly overrides it in the conversation"). The research pipeline
  remains fully runnable from `scripts/` with no dependency on the API or
  frontend. Redesigned end-to-end at the user's request partway through:
  light theme (replacing the original dark palette), a custom Three.js
  node-link hero graphic on the landing page, a standard labeled-dropdown
  filter bar on the events list (replacing an ad-hoc chip row), and the
  high-P/high-R/rest event_type-grouped view described above. Design
  tokens live in `frontend/app/globals.css`; shared components in
  `frontend/app/components/ui.tsx`.
- Test suite: 272 tests, all offline (no network calls, in-memory/temp
  SQLite, hand-built fixtures for tricky logic). Run with `pytest` from
  the project root.
- **All three test repositories (`pallets/click`, `pallets/markupsafe`,
  `venkat24k/venvdoctor`) now have both P and R fully extracted and
  scored.** Before this, only `pallets/click` had P features/scores
  computed — markupsafe and venvdoctor had R only. That gap caused a real
  bug: `GET .../events` with `high_p=true` (alone or combined with
  `high_r=true`) crashed with a 500 on any repo missing `event_p_scores`,
  because `list_events`'s `JOIN event_p_scores` had no guard for a
  not-yet-created table, unlike every other "not computed yet" path in
  `src/api/repositories.py` (`_thresholds_for_granularity`,
  `_p_features_dict`, etc., all catch `sqlite3.OperationalError`). Fixed
  by wrapping the same query in a `try/except sqlite3.OperationalError`
  that degrades to `total=0, events=[]` — filtering by an axis that
  hasn't been scored yet can only ever match zero events, never an error.
  Both fixes (the missing P data, and the crash itself) are needed
  together: the crash could resurface on any future repo added before its
  P-score run completes, so the code fix is the permanent one.
- Raw schema has grown four times since Stage 1 was first built: a
  `pr_comments` table (PR general-conversation comments GitHub's
  `comments` connection exposes separately from inline review comments),
  a `pr_closing_issues` table + `closing_issues_truncated` flag (GitHub's
  own `closingIssuesReferences` — see Section 34), a `reaction_count`
  column on `pull_requests` (GitHub's `reactions.totalCount`), and a
  `pr_cross_references` table + `cross_references_truncated` flag
  (GitHub's `crossReferencedEvent` timeline items, backing
  `later_references_count` — see Section 34). All four required deleting
  and fully re-collecting `data/raw/*.db` and rebuilding
  `data/processed/*.db` from scratch, because `CREATE TABLE IF NOT EXISTS`
  does not add a column to a table that already exists (see Section 35) —
  this is the expected procedure the next time a raw-schema column is
  added, not something to work around with an ALTER TABLE migration.

## 34. Settled Methodology Decisions

These were discussed and approved in conversation; treat as decided
unless the user reopens them — don't silently redo or second-guess them.

- **Event definition — dual granularity, not a single choice.** Both are
  generated and stored side by side so they can be compared later rather
  than betting everything on one definition:
  - `pr_bundle` (primary): each pull request is one event bundling its
    commits; a commit never associated with any PR is its own standalone
    event. (Discovered during validation: 40-60% of commits in both test
    repos never went through a PR at all — this is normal, not a
    collection bug, and is exactly why the standalone-commit half of the
    definition matters.)
  - `commit_level` (alternative): every commit is its own event, no
    bundling.
- **R features — no hard age-based exclusion.** Rejected a fixed cutoff
  (e.g. "exclude events younger than 12 months") because it would discard
  a young repository's entire history. Instead: compute R for every event
  regardless of age, and *also* compute a maturity value (how long the
  event has actually had to prove itself: observed-time-window ÷
  event-age). How maturity gets used (filtering, weighting, confidence
  interval) is deferred to the scoring stage — not decided yet.
- **P/R missing-data convention — applies to every feature, present and
  future.** Every feature is stored as a value column (NULL when not
  applicable) plus a `<feature>_status` column with exactly one of:
  - `complete` — a confident true value (0 is a valid complete value).
  - `incomplete_lower_bound` — real but undercounted, because a
    contributing raw table hit a Stage-1 truncation flag (e.g.
    `reviews_truncated`). The number is a floor, not the true count.
  - `not_applicable` — the concept doesn't exist for this event (e.g. a
    standalone commit has no PR-comment channel at all).
  A bare number or a silent 0 is never acceptable for a P/R feature.
- **Weighting — equal weights for the first pass.** P(e) and R(e) will
  initially combine features with equal weights, as a transparent
  baseline, not learned or expert-assigned weights — per Section 25/26.
  Revisit only after the evaluation stage exists to justify something more
  sophisticated.
- **Issue linkage — GitHub's own resolution, not text-guessing.**
  `issue_link_present` and `issue_has_label` both read from
  `pr_closing_issues`, populated from GitHub's `closingIssuesReferences`
  GraphQL field (the same mechanism GitHub uses to auto-close an issue on
  merge) rather than regex-matching "fixes #123" in PR bodies. Chosen over
  the regex approach specifically because it's authoritative (validates
  the issue exists, handles every closing keyword GitHub recognizes, stays
  in sync as the PR is edited) where a hand-written keyword list would be
  an assumption.
- **`issue_severity_label` was redefined to `issue_has_label`, not built
  as originally named.** Before implementing it, the real label
  vocabulary in both test repos was checked: pallets/click's issue/PR
  labels are entirely topical ('parsing', 'docs', 'shell completion', ...)
  with nothing indicating severity or priority, and pallets/markupsafe has
  zero issue labels at all (one PR, ever, labeled 'security'). A
  keyword-matched severity classifier would have been an invented category
  with almost no real support in either repository. `issue_has_label`
  measures the honest, weaker thing the data actually supports — whether
  the linked issue was labeled/triaged at all — using only
  already-collected data. Revisit a true severity/priority feature only if
  a repository with structured severity labeling (e.g. explicit P0/P1,
  GitHub's own severity labels) is added later.
- **`release_proximity` measures time until the *next* release, not since
  the last one.** Defined as seconds from an event's `occurred_at` to the
  nearest `releases.published_at` after it — "how soon did this ship,"
  not "how far into the release cycle was this." `not_applicable` when no
  later release exists in collected data (repo has no releases yet, or the
  event is more recent than every collected release) — rare in practice
  (~1% of pallets/click's events). The opposite direction (time since the
  last release) and computing both directions as separate features were
  both considered and explicitly not chosen.
- **`reaction_count` scope — PR-level reactions only, not comment-level.**
  Counts `reactions.totalCount` on the pull request itself. Reactions on
  individual comments/reviews were considered and deliberately left out of
  this first pass to keep the Stage 1 change small (would need a new
  column on `pr_comments` and `pr_review_comments`, not just
  `pull_requests`) — revisit only if PR-level reactions turn out too
  sparse to be useful once scoring/evaluation is underway. Before building
  it, real reaction counts were checked on the 20 most recent PRs/issues in
  both test repos (unlike `issue_has_label`'s label check, this one came
  back positive): reactions appear on roughly 5-25% of items in both
  repos, sparse but real, so the feature was built rather than skipped.
- **P-score normalization — percentile-rank average, not min-max/z-score.**
  Chosen because the 10 features are on wildly different scales (single
  digits for `comment_count`, thousands for `churn`) and heavily skewed
  (a handful of very large PRs would compress min-max-scaled scores of
  everything else toward 0). Each feature is converted to a percentile
  rank in `[0, 1]` within its scoring group, then averaged with equal
  weight per Section 25/26 — see `src/scoring/p_score.py`.
- **P-score grouping — scored and thresholded separately per
  `(granularity, event_type)`, never across the whole repo.** A standalone
  commit can only ever draw on 3 of the 10 features (`files_changed`,
  `churn`, `release_proximity` — it structurally has no comment/review
  channel), so scoring it against pull requests on one shared scale would
  make "high P" almost always mean "was a PR," burying the "Silent but
  Critical" quadrant (Section 3) before R is even in the picture.
  `not_applicable` features are excluded from an event's average, never
  averaged in as 0, per the existing missing-data convention above.
- **P-score threshold — top 10% per group, explicitly provisional.**
  `is_high_p` flags the top `top_percentile` (default 0.10, always passed
  explicitly, never hard-coded — Section 25) of each group's non-null
  P-scores. This is an exploratory first-pass cut for the user's planned
  P-vs-R divergence study, not a validated boundary — Section 11's
  evaluation stage is what would eventually check it against human
  judgment. Revisit the percentile once real divergence cases are being
  looked at.
- **Known limitation, accepted rather than fixed: standalone commits are
  never grouped, even when several of them are really one logical
  change.** `form_standalone_commit_events` (`src/events/formation.py`)
  makes every commit that isn't part of any PR its own independent
  event — no grouping by author, time proximity, or an unbroken
  parent→child chain. If a real update is split into, say, 3 raw commits
  pushed directly (no PR), it becomes 3 separate low-signal events instead
  of one: each has `not_applicable` for every discussion feature (no PR
  means no comment channel), and `files_changed`/`churn` each reflect only
  a third of the true combined change — diluting what could be a
  genuinely important change across three mediocre P scores instead of
  one high one. Raised and explicitly left unfixed for now (revisit only
  if it turns out to distort real results) rather than silently designing
  a grouping heuristic — changing what counts as a "candidate historical
  event" is core Phase 2 methodology, not a small tweak, so any fix needs
  its exact rule agreed first, the same way every other feature here was.
- **R's `maturity` formula, locked in before any R feature was built:**
  `(latest_commit_date − occurred_at) / (latest_commit_date − earliest_commit_date)`
  — the fraction of the repository's *entire* observed history that
  happened after this event, using `repository_data_availability`'s
  window. An event near the start of history → maturity ≈ 1 (almost
  everything collected happened after it, so R had its full chance to
  show up); an event from the very edge of collection → maturity ≈ 0 (too
  early to judge). Chosen specifically because it's the only reading of
  "observed-time-window ÷ event-age" where the ratio isn't trivially 1.0
  for every event — the other reading (raw age as a plain duration) was
  explicitly considered and rejected as not comparable across repos with
  different collection spans.
- **Two real correctness bugs `maturity`/`files_survived` hit during
  real-data verification, both instructive beyond just these two
  features:**
  1. `files_survived`'s completeness check originally asked "is this
     commit_hash present in `file_path_history`" to detect a missing
     commit — but `file_path_history` only has rows for commits that
     touched *some* file, and ~37% of pallets/markupsafe's commits are
     merges with zero recorded file changes (PyDriller doesn't diff
     merges by default). That wrongly flagged every fileless merge commit
     as `incomplete_lower_bound` (43% of all events, far higher than any
     real evidence gap). Fixed by checking `commit_annotations` instead
     (populated for *every* raw commit regardless of file count) to tell
     "genuinely missing from local history" apart from "known, but
     touched nothing" — after the fix the rate matched P's
     `files_changed` almost exactly (115 vs 115 on markupsafe), which is
     what confirmed the fix was actually correct and not just different.
     **Lesson: when checking whether evidence is "missing" for
     completeness purposes, check against a table that's populated
     unconditionally for the entity in question, not one that's only
     populated when there's something to record** — an empty result from
     the latter is ambiguous between "missing" and "genuinely nothing
     there."
  2. `maturity` produced small negative values for 12 of
     pallets/markupsafe's `pull_request` events before real-data
     verification caught it. Cause: a `pull_request` event's
     `occurred_at` is `merged_at` or `closed_at` or `created_at` (see
     `form_pr_bundle_events`), and for a PR that never merged any
     commits, that date isn't bounded by `latest_commit_date` the way a
     commit's own date always is — a still-open or commit-less-closed PR
     can have activity after the last collected commit. Fixed by treating
     `occurred_at` outside `[earliest_commit_date, latest_commit_date]`
     as `not_applicable` rather than computing an out-of-domain ratio.
     **Lesson: an event-level timestamp (`occurred_at`) is not
     interchangeable with a commit-level timestamp for bounds-checking,
     even though most events are commit-derived** — pull_request events
     specifically can fall outside a window defined purely from commit
     dates, and every future R feature that touches `occurred_at` should
     check its own bounds rather than assuming this was already handled
     elsewhere.
  3. **Performance, not correctness, but real: `subsequent_modification_count`'s
     first implementation queried the database once per event** (join
     each of the event's touched files against every other commit that
     touched them, filtered by date). Correct, and fine on
     pallets/markupsafe (1,741 events) — but on pallets/click (6,768
     events, several files with hundreds of touches) it stalled for
     minutes with no result, because a frequently-touched file's entire
     history gets redundantly re-scanned from scratch by every one of the
     many events that happen to touch it. An index on
     `candidate_events(repo_id, primary_commit_hash)` (missing before
     this — added to `src/events/schema.py`) helped one layer of it but
     wasn't the real fix. Fixed by `build_file_touch_index`
     (`src/features/r_features.py`): one query builds every file's sorted
     touch history *once* per extraction run, then every event does an
     in-memory binary search (`bisect_right`) instead of a fresh query —
     click's run went from stalling past several minutes to 1.4 seconds.
     **Lesson: a per-event query that joins against "every other commit
     touching the same file(s)" does not scale once popular files are
     touched by many events — precompute once per repository and reuse,
     the same shape of fix this codebase already uses in other stages
     (e.g. `repository_data_availability`), not a new pattern.** Check
     for this shape *before* building a feature that reasons about a
     file's/entity's full history from multiple events' perspectives, not
     after it's slow on a real repository.
- **`MIN_MATURITY_FOR_SCORING = 0.05` — the "how maturity gets used"
  question this file's R design explicitly deferred, now settled.** The
  user asked to exclude "very young" events from R scoring and asked what
  "young" should mean; rather than guessing a number, real R feature
  values were checked across maturity bands first (`event_r_features` on
  pallets/markupsafe): below ~5% maturity, events had a median of 0
  subsequent modifications and 1 release since — genuinely nothing has
  had time to happen yet, not a real low-salience signal. 0.05 was then
  presented as the recommended option (alongside a stricter 0.01 and "no
  cutoff, filter in the UI instead") and the user picked it explicitly —
  not chosen unilaterally. Implementation: events with `maturity < 0.05`
  (or unknown maturity — an event whose maturity couldn't be verified
  can't be confirmed to clear the bar either) are excluded from the
  ranking population in `compute_r_scores` (`src/scoring/r_score.py`,
  `MIN_MATURITY_FOR_SCORING`, `--min-maturity` on
  `scripts/compute_r_scores.py`) — they can never be flagged `is_high_r`,
  and just as importantly they're removed from the pool entirely so they
  can't drag down or inflate the percentile ranks of events that are
  mature enough to judge. This is a ranking-time exclusion only:
  `event_r_features` still stores a real value for every event regardless
  of age (Section 34's original "no hard cutoff" decision, about feature
  *computation*, is unchanged) — the frontend shows a "too young to rank
  yet" label instead of a score/badge for such an event, but its raw R
  feature values stay fully visible. The shared scoring core
  (`src/scoring/ranking.py: compute_group_scores`) grew a generic
  `exclude_event_ids` parameter for this — P scoring passes nothing and
  is completely unaffected (verified: the full existing P-score test
  suite still passes unchanged after the refactor).
- **`later_references_count` — GitHub's authoritative `crossReferencedEvent`
  timeline, not a regex scan of PR bodies for `#NNN`.** Before building
  either candidate, real signal density was checked on pallets/markupsafe:
  52% of PR bodies mention a `#NNN` reference (real signal, worth
  building), but only via text-guessing. The regex approach was rejected
  for the same reason `issue_link_present` rejected it — it can't validate
  the reference actually resolves, handles cross-repo references, or stays
  in sync as a PR is edited, where GitHub's own `crossReferencedEvent`
  timeline item is authoritative. Implementation: a new Stage 1 table
  `pr_cross_references` (`pr_id, source_number, referenced_at`) populated
  from `PullRequest.timelineItems(itemTypes: [CROSS_REFERENCED_EVENT])`;
  the feature counts references with `referenced_at > occurred_at` only.
  That "later" filter was checked against real data before treating it as
  correct, not assumed: 41% of markupsafe's collected cross-references (30
  of 73) happened *before* the target PR's own `occurred_at` — active
  discussion referencing a PR that hasn't merged yet is common, and
  counting those would conflate "discussed at the time" (P territory) with
  "still referenced afterward" (what R is asking). `not_applicable` for
  every non-`pull_request` event (GitHub's cross-reference timeline has no
  raw-commit equivalent).
- **`re-review_activity` (the sixth Section 2 R candidate) — checked
  against real data and explicitly not built.** Before committing to it,
  real review coverage was checked on both test repos: only 4.0% of
  markupsafe's PRs (15/377) and 14.9% of click's (283/1895) have *any*
  review at all. Too sparse in both repos to support a meaningful
  "was this re-reviewed" signal — most events would come back
  `not_applicable`, and the ones that don't wouldn't be comparable across
  a population this thin. Not revisited unless a repository with
  substantially heavier review culture is added to the study.
- **GitHub GraphQL bug found while verifying `later_references_count`:
  `timelineItems.totalCount` ignores its own `itemTypes` filter.**
  `PullRequest.timelineItems(itemTypes: [CROSS_REFERENCED_EVENT])`
  returns a `totalCount` that counts *every* timeline item on the PR
  (comments, commits, label changes, ...), not just the
  `CROSS_REFERENCED_EVENT` ones the `nodes` list is actually filtered to
  — confirmed directly against the live API (pallets/click PR #1:
  `totalCount: 7`, `nodes: []`). The first implementation compared
  `totalCount > len(nodes)` to flag `cross_references_truncated` (the same
  pattern used for every other paginated Stage 1 connection, e.g.
  `reviews_truncated`), which is wrong here specifically and silently
  flagged nearly every PR in a full click re-collection as
  `incomplete_lower_bound` even when it had zero real cross-references.
  Fixed by reading `pageInfo.hasNextPage` instead (added to the query),
  confirmed against the same live query to correctly track the
  already-`itemTypes`-filtered connection. **Lesson: don't assume a
  GraphQL connection's `totalCount` respects a filter argument just
  because every other connection in this schema does — verify against the
  live API before trusting it, the same way every other R/P feature's
  assumption was checked against real data first.**

## 35. Known Environment / Technical Gotchas

Things that cost real debugging time once; check here before re-deriving
them from scratch.

- **A processed-schema fix doesn't retroactively apply to a repo's
  existing `data/processed/<repo>.db` file — this bit the team a second
  time, from the other direction, right after Section 34's `later_references_count`
  bug taught the same lesson about raw schema.** A collaborator fixed a
  real bug in `src/processing/schema.py`: `file_path_history`'s primary
  key was `(repo_id, commit_hash, path)`, which raises
  `sqlite3.IntegrityError: UNIQUE constraint failed` on a commit that
  both deletes and re-adds the same path (two different file identities
  legitimately touching the same `(commit, path)` — hit on
  `Homebrew/BrewUI`'s real history). Fix: widen the key to
  `(repo_id, commit_hash, path, file_id)`. Pulling that fix and
  restarting both servers was **not enough** — every repo analyzed before
  the fix landed still has a `data/processed/<repo>.db` file with the old
  narrower key baked in (`CREATE TABLE IF NOT EXISTS` never alters an
  existing table), so re-running `normalize` against any of them would
  still hit the same crash the fix was supposed to eliminate, exactly
  like a stale raw schema would. **Resolved for every repo on this
  machine** by deleting every `data/processed/*.db` (never `data/raw/`)
  and rebuilding from the already-collected raw data via
  `run_full_pipeline(..., stages=non-collect)` — verified clean across 9
  repos including `pallets/streamlit` (26,759 divergence-classified
  events, by far the largest and most varied real history collected in
  this project), which also served as a real-data audit of every other
  `PRIMARY KEY`/`UNIQUE` constraint in the schema (`src/collection/schema.py`,
  `src/processing/schema.py`, `src/events/schema.py`) for the same class
  of "two legitimate real rows collide under this key" risk — none
  surfaced. **Standing rule, not just for this one incident: after
  pulling or making any change to a `CREATE TABLE` statement in
  `src/*/schema.py`, check whether any `data/processed/*.db` (or
  `data/raw/*.db` for a raw-schema change) predates it, and rebuild those
  specifically — restarting the servers alone is never sufficient for a
  schema change, only for a Python logic change.**
- **Windows' 260-character MAX_PATH breaks `git clone` on real repositories
  with long file paths** (confirmed against `pallets/streamlit`'s own
  `e2e_playwright/__snapshots__/...` test-snapshot filenames). Git clones
  the objects fine, then fails to check specific files out ("unable to
  create file ...: Filename too long") and the whole clone command still
  exits non-zero — from the API/frontend this surfaced as a "Clone
  repository" pipeline failure with no further detail; the real message
  was only visible in the backend's own stdout/stderr log
  (`/tmp/backend.log` in this dev setup), not in the job's `error` field.
  Fixed once, generically, in `src/collection/git_collector.py:
  ensure_local_clone` — every command that writes the working tree
  (`clone`, `reset --hard`) now passes `-c core.longpaths=true`, git's own
  opt-in workaround; needs no elevated permissions or Windows-wide
  registry change (`LongPathsEnabled`), unlike some guides suggest. A
  clone that failed before this fix leaves a broken partial directory
  under `data/raw/_clones/<repo>/` (`.git` present, working tree
  incomplete) — safe to delete and let `ensure_local_clone` re-clone from
  scratch, since that directory is a regenerable git mirror, not raw
  evidence itself (the SQLite files under `data/raw/*.db` are the actual
  evidence store).
- **`localhost` is unreliable in this dev/agent environment.** Both `curl`
  and an actual browser can hang indefinitely resolving/connecting to
  `localhost`, while `127.0.0.1` works reliably every time. Bind servers
  and configure clients — including CORS `allow_origins` — using
  `127.0.0.1` explicitly, not `localhost`.
- **Next.js dev-mode hot-reload fails silently in this sandbox.**
  `npm run dev` (Turbopack) serves pages that render correctly but never
  hydrate — zero client-side JS executes, no console errors, nothing is
  interactive. Confirmed environment-specific: a production build
  (`npm run build && npm run start`) works with zero errors. If UI testing
  shows "page loads but nothing is clickable," check this before assuming
  a code bug.
- **PyDriller hangs indefinitely given a remote git URL directly**
  (observed on this Windows setup — no CPU, no network activity, no
  error, just hangs). Always clone with plain `git` first
  (`src/collection/git_collector.py: ensure_local_clone`) and pass
  PyDriller a local path only. `collect_git_history()` raises immediately
  if given anything that looks like a remote URL, specifically so this
  can't silently reproduce.
- **PyDriller's `ModifiedFile.filename` is a basename only** (e.g.
  `__init__.py`, not the full path) — collides across directories with
  the same filename. Use `new_path`/`old_path` instead (already fixed).
- **Compare commit timestamps via `author_date_utc`, never raw
  `author_date`.** The raw field preserves each committer's local UTC
  offset, which sorts *incorrectly* as plain text against a different
  offset (a real bug this caused: a file's `MODIFY` sorted before its own
  `ADD`). `author_date_utc` is the UTC-normalized column added
  specifically for correct chronological ordering.
- **PyGithub (the library) was abandoned in favor of raw GraphQL/REST.**
  It has real, confirmed bugs on this project: touching `Issue.pull_request`
  silently triggers one extra full API call per issue (a lazy-completion
  property), and it showed unexplained internal slowness/hangs unrelated
  to that. `src/collection/github_collector.py` talks to GitHub directly
  via `requests`. Don't reintroduce PyGithub without re-verifying these
  are actually gone.
- **GitHub GraphQL rate-limit exhaustion returns HTTP 200 with an
  `errors` body**, not 403/429 — must be checked in the parsed JSON, not
  just the HTTP status code (`_graphql()` in `github_collector.py` already
  handles this).
- **Raw/processed DB file naming:** `data/{raw,processed}/{owner}__{repo}.db`
  (double underscore), via `src/pipeline.py: default_db_paths()`.
