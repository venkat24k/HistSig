import pytest

from src.api import repositories
from tests.api.conftest import seed_repo


def test_list_repositories_empty(data_dir):
    assert repositories.list_repositories() == []


def test_list_repositories_returns_seeded_repo(data_dir):
    seed_repo(data_dir, "o__r")

    repos = repositories.list_repositories()

    assert len(repos) == 1
    assert repos[0]["safe_name"] == "o__r"
    assert repos[0]["counts"]["commits"] == 1
    assert repos[0]["counts"]["pull_requests"] == 1
    assert repos[0]["contributor_count"] == 1
    assert repos[0]["event_counts"] == {"pr_bundle": 1}


def test_get_repository_not_found_raises(data_dir):
    with pytest.raises(repositories.RepositoryNotFound):
        repositories.get_repository("does_not_exist")


def test_get_repository_without_processed_data(data_dir):
    seed_repo(data_dir, "o__r", with_processed=False)

    repo = repositories.get_repository("o__r")

    assert repo["contributor_count"] is None
    assert repo["event_counts"] == {}


def test_list_events_filters_by_granularity_and_type(data_dir):
    seed_repo(data_dir, "o__r")

    result = repositories.list_events("o__r", granularity="pr_bundle", event_type=None, limit=50, offset=0)
    assert result["total"] == 1
    assert result["events"][0]["title"] == "Add feature"
    assert result["events"][0]["author"] == {"name": "Bob", "github_login": "bob", "is_bot": False}

    empty = repositories.list_events("o__r", granularity="commit_level", event_type=None, limit=50, offset=0)
    assert empty["total"] == 0

    filtered_out = repositories.list_events("o__r", granularity="pr_bundle", event_type="standalone_commit", limit=50, offset=0)
    assert filtered_out["total"] == 0


def test_list_events_without_processed_data_raises(data_dir):
    seed_repo(data_dir, "o__r", with_processed=False)

    with pytest.raises(repositories.RepositoryNotFound):
        repositories.list_events("o__r", granularity="pr_bundle", event_type=None, limit=50, offset=0)


def test_get_event_includes_commits_and_pr_detail(data_dir):
    seed_repo(data_dir, "o__r")
    event_id = repositories.list_events("o__r", "pr_bundle", None, 50, 0)["events"][0]["id"]

    event = repositories.get_event("o__r", event_id)

    assert event["title"] == "Add feature"
    assert event["pr_detail"]["state"] == "closed"
    assert event["pr_detail"]["body"] == "desc"
    assert len(event["commits"]) == 1
    assert event["commits"][0]["hash"] == "c1"
    assert event["commits"][0]["author_name"] == "Alice"


def test_get_event_not_found_raises(data_dir):
    seed_repo(data_dir, "o__r")
    with pytest.raises(repositories.RepositoryNotFound):
        repositories.get_event("o__r", 9999)
