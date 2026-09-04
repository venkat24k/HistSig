"""End-to-end pipeline orchestration: collection -> normalization -> event
formation, for one repository. Shared by the CLI scripts and the API
backend (src/api/) so the two never drift apart — each just supplies a
different `on_progress` callback (print statements vs. job-state updates).
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
from src.events.orchestrate import form_and_store_events
from src.events.schema import create_schema as create_events_schema
from src.processing.normalize import normalize_repository
from src.processing.schema import connect as connect_processed

ProgressCallback = Callable[[str, dict], None]


def default_db_paths(owner_repo: str, data_dir: str = "data") -> tuple[str, str]:
    safe_name = owner_repo.replace("/", "__")
    return f"{data_dir}/raw/{safe_name}.db", f"{data_dir}/processed/{safe_name}.db"


DEFAULT_STAGES = ("collect", "normalize", "events")


def run_full_pipeline(
    repo_url: str, raw_db_path: str, token: str, processed_db_path: str | None = None,
    branch: str | None = None, stages: tuple[str, ...] = DEFAULT_STAGES,
    on_progress: ProgressCallback | None = None,
) -> dict:
    """`stages` controls which of collect/normalize/events actually run —
    e.g. a plain Stage 1 collection pass uses `stages=("collect",)` and
    never needs `processed_db_path` at all. `normalize`/`events` each
    require every stage before them to have produced data at some point
    (this call or an earlier one against the same db paths)."""
    if ("normalize" in stages or "events" in stages) and processed_db_path is None:
        raise ValueError("processed_db_path is required when stages includes 'normalize' or 'events'")

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
    processed_conn = connect_processed(processed_db_path) if ("normalize" in stages or "events" in stages) else None

    if "normalize" in stages:
        progress("normalizing")
        normalize_summary = normalize_repository(raw_conn, processed_conn, repo_id)
        progress("normalized", **normalize_summary)
        result["normalize"] = normalize_summary

    if "events" in stages:
        progress("forming_events")
        create_events_schema(processed_conn)
        events_summary = form_and_store_events(raw_conn, processed_conn, repo_id)
        result["events"] = events_summary

    progress("done")
    return result
