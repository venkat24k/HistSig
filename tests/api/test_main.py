"""API smoke tests. Deliberately does not exercise the success path of
POST /api/pipeline/run — FastAPI's TestClient runs BackgroundTasks
synchronously, so a valid request would actually attempt a live GitHub
collection. Only the validation-failure path (which returns before a
background task is ever scheduled) is tested here."""

from fastapi.testclient import TestClient

from src.api.main import app
from tests.api.conftest import seed_repo


def test_health():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_run_pipeline_rejects_bad_url_before_scheduling_anything():
    client = TestClient(app)
    resp = client.post("/api/pipeline/run", json={"repo_url": "https://gitlab.com/o/r"})
    assert resp.status_code == 400


def test_job_status_not_found():
    client = TestClient(app)
    resp = client.get("/api/pipeline/jobs/does-not-exist")
    assert resp.status_code == 404


def test_list_repositories_empty(data_dir):
    client = TestClient(app)
    resp = client.get("/api/repositories")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_repository_not_found(data_dir):
    client = TestClient(app)
    resp = client.get("/api/repositories/does_not_exist")
    assert resp.status_code == 404


def test_events_rejects_bad_granularity(data_dir):
    seed_repo(data_dir, "o__r")
    client = TestClient(app)
    resp = client.get("/api/repositories/o__r/events", params={"granularity": "nonsense"})
    assert resp.status_code == 400


def test_full_repository_and_event_flow(data_dir):
    seed_repo(data_dir, "o__r")
    client = TestClient(app)

    repo_resp = client.get("/api/repositories/o__r")
    assert repo_resp.status_code == 200
    assert repo_resp.json()["counts"]["pull_requests"] == 1

    events_resp = client.get("/api/repositories/o__r/events")
    assert events_resp.status_code == 200
    events = events_resp.json()["events"]
    assert len(events) == 1

    detail_resp = client.get(f"/api/repositories/o__r/events/{events[0]['id']}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["title"] == "Add feature"
