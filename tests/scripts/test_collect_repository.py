import pytest

from scripts.collect_repository import parse_owner_repo


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/pallets/click", "pallets/click"),
    ("https://github.com/pallets/click.git", "pallets/click"),
    ("https://github.com/pallets/click/", "pallets/click"),
    ("git@github.com:pallets/click.git", "pallets/click"),
    ("https://github.com/pallets/click/tree/main", "pallets/click"),
    ("https://github.com/pallets/click/pull/123", "pallets/click"),
])
def test_parse_owner_repo_handles_common_url_shapes(url, expected):
    assert parse_owner_repo(url) == expected


def test_parse_owner_repo_rejects_non_github_url():
    with pytest.raises(ValueError):
        parse_owner_repo("https://gitlab.com/pallets/click")
