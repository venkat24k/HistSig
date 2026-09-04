"""FastAPI backend for Digital Ghost's demo frontend.

Run with: uvicorn src.api.main:app --reload --port 8000

Read-only over the same data/raw and data/processed SQLite files the CLI
scripts and tests use — this process does not own or lock that data, and
the research pipeline (src/collection, src/processing, src/events) remains
fully runnable without this API ever existing, per CLAUDE.md Section 8:
"The research engine must remain independently executable without the
frontend."
"""

import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api import jobs, repositories
from src.collection.github_collector import parse_owner_repo

load_dotenv()

app = FastAPI(title="Digital Ghost API")

# Both hostnames are allowed since "localhost" vs "127.0.0.1" resolution
# is inconsistent across browsers/OSes for local dev — this app is never
# deployed with real user origins, so there's no security tradeoff here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "github_token_configured": bool(os.environ.get("GITHUB_TOKEN"))}


class RunRequest(BaseModel):
    repo_url: str


@app.post("/api/pipeline/run")
def start_pipeline(req: RunRequest, background_tasks: BackgroundTasks):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise HTTPException(500, "GITHUB_TOKEN is not configured on the server (see .env.example)")
    try:
        parse_owner_repo(req.repo_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    job = jobs.create_job(req.repo_url)
    background_tasks.add_task(jobs.run_job, job.id, token)
    return {"job_id": job.id}


@app.get("/api/pipeline/jobs")
def list_jobs():
    return [
        {"id": j.id, "repo_url": j.repo_url, "status": j.status, "stage": j.stage, "created_at": j.created_at}
        for j in jobs.list_jobs()
    ]


@app.get("/api/pipeline/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return {
        "id": job.id, "repo_url": job.repo_url, "status": job.status, "stage": job.stage,
        "log": job.log, "result": job.result, "error": job.error, "created_at": job.created_at,
    }


@app.get("/api/repositories")
def list_repositories():
    return repositories.list_repositories()


@app.get("/api/repositories/{safe_name}")
def get_repository(safe_name: str):
    try:
        return repositories.get_repository(safe_name)
    except repositories.RepositoryNotFound:
        raise HTTPException(404, f"repository {safe_name!r} not found")


@app.get("/api/repositories/{safe_name}/events")
def list_events(safe_name: str, granularity: str = "pr_bundle", event_type: str | None = None, limit: int = 50, offset: int = 0):
    if granularity not in ("pr_bundle", "commit_level"):
        raise HTTPException(400, "granularity must be 'pr_bundle' or 'commit_level'")
    if not (1 <= limit <= 500):
        raise HTTPException(400, "limit must be between 1 and 500")
    try:
        return repositories.list_events(safe_name, granularity, event_type, limit, offset)
    except repositories.RepositoryNotFound as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/repositories/{safe_name}/events/{event_id}")
def get_event(safe_name: str, event_id: int):
    try:
        return repositories.get_event(safe_name, event_id)
    except repositories.RepositoryNotFound as exc:
        raise HTTPException(404, str(exc))
