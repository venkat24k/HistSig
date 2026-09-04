"""In-memory pipeline job tracking for the API backend.

A collection run takes 1-6+ minutes, so it can't run inline in a request
handler. This is a deliberately minimal background-job mechanism — a
single in-process dict guarded by a lock, run via FastAPI's BackgroundTasks
— appropriate for a local single-user research/demo tool. It does not
survive a server restart and does not scale beyond one process; a real
task queue (Celery, etc.) would be the CLAUDE.md Section 21 "profile
before optimizing" upgrade if this backend ever needed to be multi-user or
long-running, not something to build preemptively.
"""

import datetime
import threading
import uuid
from dataclasses import dataclass, field

from src.collection.github_collector import parse_owner_repo
from src.pipeline import default_db_paths, run_full_pipeline


@dataclass
class Job:
    id: str
    repo_url: str
    status: str = "pending"  # pending | running | done | error
    stage: str = "pending"
    log: list[dict] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create_job(repo_url: str) -> Job:
    job = Job(id=str(uuid.uuid4()), repo_url=repo_url)
    with _lock:
        _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> list[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


def run_job(job_id: str, token: str) -> None:
    job = get_job(job_id)
    if job is None:
        return

    with _lock:
        job.status = "running"

    def on_progress(stage: str, data: dict) -> None:
        with _lock:
            job.stage = stage
            job.log.append({"stage": stage, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(), **data})

    try:
        owner_repo = parse_owner_repo(job.repo_url)
        raw_db_path, processed_db_path = default_db_paths(owner_repo)
        result = run_full_pipeline(
            repo_url=job.repo_url, raw_db_path=raw_db_path, processed_db_path=processed_db_path,
            token=token, on_progress=on_progress,
        )
        with _lock:
            job.status = "done"
            job.result = result
    except Exception as exc:
        with _lock:
            job.status = "error"
            job.error = str(exc)
