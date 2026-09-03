# CLAUDE.md — Digital Ghost / HistSig Project Constitution

This file is the long-term governing document for this repository. It applies to
every future Claude Code session working here. When instructions elsewhere
conflict with this file, this file wins unless the user explicitly overrides it
in the conversation.

This is a **research project first**, with a demonstration application built
around it. Read Section 5 and Section 31 before doing anything else — they
define the priority order that governs every other decision in this document.

---

## 1. Project Identity

- **Project name:** Digital Ghost
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
methodology and its empirical validation.** Digital Ghost is the
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

Neo4j is part of the Digital Ghost architecture, representing relationships
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

## 8. Digital Ghost Role

Digital Ghost is the platform that demonstrates HistSig. Eventually it should
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

Only after the research core works should the complete Digital Ghost
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

**Supporting infrastructure (Digital Ghost):** repository collection,
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
