from src.divergence.storage import insert_divergence


def _row(event_id, granularity="pr_bundle", event_type="pull_request", p_score=0.6, r_score=0.7, is_high_p=1, is_high_r=1, quadrant="truly_important"):
    return {
        "event_id": event_id, "granularity": granularity, "event_type": event_type,
        "p_score": p_score, "r_score": r_score, "is_high_p": is_high_p, "is_high_r": is_high_r, "quadrant": quadrant,
    }


def _insert_event(conn, event_id, repo_id=1):
    conn.execute(
        "INSERT INTO candidate_events (id, repo_id, granularity, event_type, source_pr_number, primary_commit_hash, title, occurred_at) "
        "VALUES (?, ?, 'pr_bundle', 'pull_request', NULL, NULL, 't', '2024-01-01')",
        (event_id, repo_id),
    )
    conn.commit()


def test_insert_divergence_is_idempotent(processed_conn):
    _insert_event(processed_conn, 1)
    rows = [_row(1)]
    insert_divergence(processed_conn, repo_id=1, rows=rows)
    insert_divergence(processed_conn, repo_id=1, rows=rows)

    assert processed_conn.execute("SELECT COUNT(*) FROM event_divergence").fetchone()[0] == 1
    row = processed_conn.execute("SELECT quadrant FROM event_divergence WHERE event_id=1").fetchone()
    assert row == ("truly_important",)


def test_insert_divergence_does_not_clobber_other_repo(processed_conn):
    _insert_event(processed_conn, 1, repo_id=1)
    _insert_event(processed_conn, 2, repo_id=2)
    insert_divergence(processed_conn, repo_id=1, rows=[_row(1, quadrant="routine_noise")])
    insert_divergence(processed_conn, repo_id=2, rows=[_row(2, quadrant="truly_important")])

    assert processed_conn.execute("SELECT COUNT(*) FROM event_divergence").fetchone()[0] == 2

    insert_divergence(processed_conn, repo_id=1, rows=[_row(1, quadrant="discussed_but_forgotten")])
    assert processed_conn.execute("SELECT COUNT(*) FROM event_divergence").fetchone()[0] == 2
    assert processed_conn.execute("SELECT quadrant FROM event_divergence WHERE event_id=2").fetchone()[0] == "truly_important"
    assert processed_conn.execute("SELECT quadrant FROM event_divergence WHERE event_id=1").fetchone()[0] == "discussed_but_forgotten"
