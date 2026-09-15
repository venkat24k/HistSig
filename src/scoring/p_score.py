"""P-score computation (Phase 3, first half): a single 0-1 attention score
per event, derived from the 10 P features already extracted.

This is deliberately P-only. P and R must stay conceptually separate
(CLAUDE.md Section 2/25) — this is not "the HistSig score," just the P
half of it. See src/scoring/ranking.py for the scoring algorithm itself
(percentile-rank average per group, top-percentile threshold) — identical
between P and R, so it lives in one shared place; this module only states
P's own feature list and table.
"""

import sqlite3

from src.scoring.ranking import DEFAULT_TOP_PERCENTILE, compute_group_scores, percentile_ranks

# Mirrors src/features/storage.py's _FEATURE_COLUMNS. Kept as a separate
# list (not imported) so this module states its own contract explicitly —
# consistent with how src/api/repositories.py already does the same for
# the same reason.
_P_FEATURE_NAMES = (
    "comment_count", "distinct_commenters", "reviewer_count", "review_rounds",
    "files_changed", "churn", "issue_link_present", "issue_has_label",
    "release_proximity", "reaction_count",
)

# Re-exported for backward compatibility with existing callers/tests that
# import these names from this module specifically.
_percentile_ranks = percentile_ranks


def compute_p_scores(processed_conn: sqlite3.Connection, repo_id: int, top_percentile: float = DEFAULT_TOP_PERCENTILE) -> dict:
    return compute_group_scores(processed_conn, repo_id, "event_p_features", _P_FEATURE_NAMES, top_percentile)
