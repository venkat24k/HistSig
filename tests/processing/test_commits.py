from src.processing.commits import detect_revert


def test_detect_revert_with_standard_git_revert_message():
    message = 'Revert "Add feature X"\n\nThis reverts commit abc1234567890abcdef1234567890abcdef1234.\n'
    result = detect_revert(message)
    assert result.is_revert is True
    assert result.reverts_commit_hash == "abc1234567890abcdef1234567890abcdef1234"


def test_detect_revert_manual_revert_without_hash_line():
    result = detect_revert("Revert the bad change from yesterday")
    assert result.is_revert is True
    assert result.reverts_commit_hash is None


def test_detect_revert_not_a_revert():
    result = detect_revert("Add a new feature")
    assert result.is_revert is False
    assert result.reverts_commit_hash is None


def test_detect_revert_handles_empty_message():
    result = detect_revert("")
    assert result.is_revert is False
    assert result.reverts_commit_hash is None
