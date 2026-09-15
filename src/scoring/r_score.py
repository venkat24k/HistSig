"""R-score computation (Phase 3, second half): a single 0-1
historical-salience score per event, derived from R features.

This is deliberately R-only. P and R must stay conceptually separate
(CLAUDE.md Section 2/25) — this is not "the HistSig score," just the R
half of it, mirroring src/scoring/p_score.py's method exactly at the
user's explicit request ("do everything we did for P" for R too). See
src/scoring/ranking.py for the scoring algorithm itself.

Deliberate difference from P: `maturity` is excluded from the averaged
feature set. It isn't a weighted R feature — it's context every other R
feature needs when read (CLAUDE.md Section 34): a low `files_survived`
count for a `maturity` ≈ 0 event means "too early to judge," not "this
didn't matter." Averaging it in as if it were itself a salience signal
would give young events an artificial boost (a brand-new event trivially
has `maturity` ≈ 0, which is not the same claim as "low salience") and
double-counts the same time-bias the other three features already carry
for free. Only `files_survived`, `subsequent_modification_count`, and
`releases_since_count` are actually being ranked.

Second layer, added after the first version shipped and the user asked
"can we exclude very young events" (i.e. "how maturity gets used" —
CLAUDE.md Section 34's originally-deferred question, now settled):
events with `maturity` below `MIN_MATURITY_FOR_SCORING` are excluded from
the ranking population entirely — they can never be flagged `is_high_r`,
and (just as importantly) they don't drag down the percentile ranks of
events that *are* mature enough to judge. The cutoff was chosen from real
data, not guessed: below ~5% maturity, pallets/markupsafe's events had a
median of 0 subsequent modifications and 1 release since — genuinely
nothing has had time to happen yet, not a real low-salience signal. This
is a scoring/ranking-time exclusion only: `event_r_features` still stores
a real value for every event regardless of age (the original "no hard
cutoff" decision governing feature *computation* is untouched — see
`compute_maturity` in r_features.py), so nothing about raw evidence is
hidden; only which events compete for "high R" changes. An event with
unknown maturity (`maturity_status` != "complete" — e.g. a `pull_request`
whose `occurred_at` falls outside the observed commit window) is also
excluded, for the same reason: unverifiable maturity can't be confirmed
to clear the bar either.
"""

import sqlite3

from src.scoring.ranking import DEFAULT_TOP_PERCENTILE, compute_group_scores

# Mirrors src/features/storage.py's _R_FEATURE_COLUMNS minus "maturity" —
# see this module's docstring for why maturity is excluded from the
# averaged features (as opposed to used to filter the ranking population,
# which is MIN_MATURITY_FOR_SCORING below).
_R_FEATURE_NAMES = ("files_survived", "subsequent_modification_count", "releases_since_count", "later_references_count")

MIN_MATURITY_FOR_SCORING = 0.05


def compute_r_scores(
    processed_conn: sqlite3.Connection,
    repo_id: int,
    top_percentile: float = DEFAULT_TOP_PERCENTILE,
    min_maturity: float = MIN_MATURITY_FOR_SCORING,
) -> dict:
    too_young = {
        r[0] for r in processed_conn.execute(
            "SELECT event_id FROM event_r_features WHERE repo_id = ? AND (maturity IS NULL OR maturity < ?)",
            (repo_id, min_maturity),
        )
    }
    return compute_group_scores(
        processed_conn, repo_id, "event_r_features", _R_FEATURE_NAMES, top_percentile, exclude_event_ids=too_young
    )
