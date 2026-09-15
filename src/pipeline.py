"""End-to-end pipeline orchestration: collection -> normalization -> event
formation -> P/R feature extraction -> P/R scoring -> divergence
classification, for one repository. Shared by the CLI scripts and the API
backend (src/api/) so the two never drift apart — each just supplies a
different `on_progress` callback (print statements vs. job-state updates).

Every stage past "collect" reuses the exact same functions the standalone
`scripts/*.py` entry points call (`extract_p_features`, `compute_r_scores`,
`classify_divergence`, ...) — this module is pure orchestration, no
methodology logic of its own, so those functions' own tests are what
actually cover correctness. What's new here is wiring them together so
"analyze this repository" (the API's one-click flow, and the default for
any future caller) produces a repository with real P/R scores and a
divergence classification, not just candidate events — before this, only
whichever repos happened to have `scripts/extract_features.py` etc. run
against them by hand had P data at all (see CLAUDE.md Section 34).
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from src.collection.git_collector import collect_git_history, ensure_local_clone
from src.collection.github_collector import (
    collect_issues,
    collect_pull_requests,
    collect_releases,
    get_repo_metadata,
    get_session,
    parse_owner_repo,
)
from src.collection.schema import connect as connect_raw
from src.collection.storage import insert_commits, insert_issues, insert_pull_requests, insert_releases, upsert_repository
from src.divergence.classify import classify_divergence
from src.divergence.schema import reset_schema as reset_divergence_schema
from src.divergence.storage import insert_divergence
from src.events.orchestrate import form_and_store_events
from src.events.schema import create_schema as create_events_schema
from src.features.extract import extract_p_features, extract_r_features
from src.features.schema import reset_r_schema as reset_r_features_schema
from src.features.schema import reset_schema as reset_p_features_schema
from src.processing.normalize import normalize_repository
from src.processing.schema import connect as connect_processed
from src.scoring.p_score import compute_p_scores
from src.scoring.r_score import compute_r_scores
from src.scoring.schema import reset_r_schema as reset_r_scoring_schema
from src.scoring.schema import reset_schema as reset_p_scoring_schema
from src.scoring.storage import insert_p_scores, insert_r_scores

ProgressCallback = Callable[[str, dict], None]


def default_db_paths(owner_repo: str, data_dir: str = "data") -> tuple[str, str]:
    safe_name = owner_repo.replace("/", "__")
    return f"{data_dir}/raw/{safe_name}.db", f"{data_dir}/processed/{safe_name}.db"


DEFAULT_STAGES = (
    "collect", "normalize", "events",
    "p_features", "r_features", "p_scores", "r_scores", "divergence",
)

# Stages that read/write the processed database — any of these requires
# processed_db_path.
_PROCESSED_STAGES = {"normalize", "events", "p_features", "r_features", "p_scores", "r_scores", "divergence"}


def run_full_pipeline(
    repo_url: str, raw_db_path: str, token: str, processed_db_path: str | None = None,
    branch: str | None = None, stages: tuple[str, ...] = DEFAULT_STAGES,
    on_progress: ProgressCallback | None = None,
) -> dict:
    """`stages` controls which stages actually run — e.g. a plain Stage 1
    collection pass uses `stages=("collect",)` and never needs
    `processed_db_path` at all. Every stage after `collect` requires every
    stage before it to have produced data at some point (this call or an
    earlier one against the same db paths); `p_scores`/`r_scores`/
    `divergence` in particular need `p_features`/`r_features` to have run
    first (this call or a previous one) since they read
    `event_p_features`/`event_r_features`, not raw evidence directly."""
    if _PROCESSED_STAGES & set(stages) and processed_db_path is None:
        raise ValueError(f"processed_db_path is required when stages includes any of {sorted(_PROCESSED_STAGES)}")

    def progress(stage: str, **data) -> None:
        if on_progress:
            on_progress(stage, data)

    owner_repo = parse_owner_repo(repo_url)
    progress("starting", owner_repo=owner_repo)

    raw_conn = connect_raw(raw_db_path)
    result: dict = {"owner_repo": owner_repo}

    if "collect" in stages:
        session = get_session(token)
        repo_meta = get_repo_metadata(session, owner_repo)
        repo_id = upsert_repository(raw_conn, url=repo_url, name=owner_repo, default_branch=repo_meta.get("default_branch"))

        clone_dir = Path(raw_db_path).parent / "_clones" / owner_repo.replace("/", "__")
        progress("cloning")
        local_path = ensure_local_clone(repo_meta["clone_url"], str(clone_dir))

        progress("collecting")
        collectors = {
            "commits": lambda: collect_git_history(local_path, only_in_branch=branch),
            "issues": lambda: collect_issues(session, owner_repo),
            "pull_requests": lambda: collect_pull_requests(session, owner_repo),
            "releases": lambda: collect_releases(session, owner_repo),
        }
        with ThreadPoolExecutor(max_workers=len(collectors)) as pool:
            futures = {name: pool.submit(fn) for name, fn in collectors.items()}
            collected = {name: future.result() for name, future in futures.items()}

        insert_commits(raw_conn, repo_id, collected["commits"])
        progress("collected", entity="commits", count=len(collected["commits"]))
        insert_issues(raw_conn, repo_id, collected["issues"])
        progress("collected", entity="issues", count=len(collected["issues"]))
        insert_pull_requests(raw_conn, repo_id, collected["pull_requests"])
        progress("collected", entity="pull_requests", count=len(collected["pull_requests"]))
        insert_releases(raw_conn, repo_id, collected["releases"])
        progress("collected", entity="releases", count=len(collected["releases"]))
        result["counts"] = {name: len(records) for name, records in collected.items()}
    else:
        repo_row = raw_conn.execute("SELECT id FROM repositories WHERE url = ?", (repo_url,)).fetchone()
        if repo_row is None:
            raise ValueError(f"No repository row for {repo_url!r} in {raw_db_path} — run the 'collect' stage first.")
        repo_id = repo_row[0]

    result["repo_id"] = repo_id
    processed_conn = connect_processed(processed_db_path) if (_PROCESSED_STAGES & set(stages)) else None

    if "normalize" in stages:
        progress("normalizing")
        normalize_summary = normalize_repository(raw_conn, processed_conn, repo_id)
        progress("normalized", **normalize_summary)
        result["normalize"] = normalize_summary

    if "events" in stages:
        progress("forming_events")
        create_events_schema(processed_conn)
        events_summary = form_and_store_events(raw_conn, processed_conn, repo_id)
        progress("formed_events", **events_summary)
        result["events"] = events_summary

    if "p_features" in stages:
        progress("extracting_p_features")
        reset_p_features_schema(processed_conn)
        p_features_summary = extract_p_features(raw_conn, processed_conn, repo_id)
        progress("extracted_p_features", **p_features_summary)
        result["p_features"] = p_features_summary

    if "r_features" in stages:
        progress("extracting_r_features")
        reset_r_features_schema(processed_conn)
        r_features_summary = extract_r_features(raw_conn, processed_conn, repo_id)
        progress("extracted_r_features", **r_features_summary)
        result["r_features"] = r_features_summary

    if "p_scores" in stages:
        progress("scoring_p")
        reset_p_scoring_schema(processed_conn)
        p_score_result = compute_p_scores(processed_conn, repo_id)
        insert_p_scores(processed_conn, repo_id, p_score_result["score_rows"], p_score_result["threshold_rows"])
        progress("scored_p", **p_score_result["summary"])
        result["p_scores"] = p_score_result["summary"]

    if "r_scores" in stages:
        progress("scoring_r")
        reset_r_scoring_schema(processed_conn)
        r_score_result = compute_r_scores(processed_conn, repo_id)
        insert_r_scores(processed_conn, repo_id, r_score_result["score_rows"], r_score_result["threshold_rows"])
        progress("scored_r", **r_score_result["summary"])
        result["r_scores"] = r_score_result["summary"]

    if "divergence" in stages:
        progress("classifying_divergence")
        reset_divergence_schema(processed_conn)
        # p_scores/r_scores are declared in DEFAULT_STAGES before
        # divergence, but a caller can in principle request `divergence`
        # on its own against a db where scoring already ran previously —
        # same "requires every stage before it to have run at some point"
        # contract as normalize/events already have.
        divergence_result = classify_divergence(processed_conn, repo_id)
        insert_divergence(processed_conn, repo_id, divergence_result["rows"])
        progress("classified_divergence", **divergence_result["summary"])
        result["divergence"] = divergence_result["summary"]

    progress("done")
    return result
