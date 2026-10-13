"""Informal evaluation helper: compares HistSig's P/R scores and divergence
classification against a project's own changelog-cited PRs, used as a free,
pre-existing (but noisy and incomplete) proxy for "a real maintainer declared
this change notable."

This is NOT the formal human-annotated evaluation CLAUDE.md Section 11
describes (that needs its own experimental design, discussed and approved
separately) -- it's a cheap sanity check: does HistSig score changelog-cited
PRs higher than the rest of the repository, more than chance would predict?
A changelog line is a weak positive label (most genuinely significant
changes never get a changelog mention, and plenty of changelog mentions are
routine), so treat every number here as a signal check, not a certified
accuracy figure.

Usage:
    python scripts/evaluate_against_changelog.py \
        --processed-db data/processed/pallets__click.db \
        --citations-file data/results/changelog_citations/pallets__click.json \
        [--human-era-only]

Requires the processed db to already have P scores, R scores, and
divergence classification (i.e. the full pipeline has run). The citations
file is produced by hand (see data/results/changelog_citations/*.json for
the format) -- changelog citation syntax differs per project (RST `:pr:`
roles, MyST `{pr}` roles, Markdown `(#NNN)` parens, towncrier links), so
this script doesn't try to parse changelogs itself, only compare an
already-extracted PR number list against scored events.

Reports precision/recall/F1 against the cited-PR population, not bare
"accuracy" -- with citation rates typically under 15%, a trivial
always-negative classifier beats "accuracy" alone without being useful
(see data/results/changelog_citations/*_report.json for worked examples of
why this matters). Writes a JSON report next to the citations file.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def confusion(rows, cited_set, predicate):
    tp = sum(1 for r in rows if r["source_pr_number"] in cited_set and predicate(r))
    fp = sum(1 for r in rows if r["source_pr_number"] not in cited_set and predicate(r))
    positives = sum(1 for r in rows if r["source_pr_number"] in cited_set)
    n = len(rows)
    fn = positives - tp
    tn = n - positives - fp
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / positives if positives else None
    f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None
    accuracy = (tp + tn) / n if n else None
    baseline_accuracy = (n - positives) / n if n else None
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "accuracy": accuracy, "trivial_always_negative_baseline_accuracy": baseline_accuracy,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--processed-db", required=True)
    parser.add_argument("--citations-file", required=True)
    parser.add_argument(
        "--human-era-only", action="store_true",
        help="Restrict both the cited-PR list and the population to events before "
             "the citations file's human_era_cutoff (if present) -- excludes any "
             "bot/synthetic-release-era activity from the comparison entirely.",
    )
    args = parser.parse_args()

    citations = json.loads(Path(args.citations_file).read_text())
    repo = citations["repo"]

    if args.human_era_only:
        if not citations.get("human_era_cutoff"):
            raise SystemExit(f"{args.citations_file} has no human_era_cutoff -- check release authorship "
                              f"for a bot/synthetic-era split before using --human-era-only.")
        cited_prs = citations.get("human_era_cited_prs")
        if cited_prs is None:
            raise SystemExit(f"{args.citations_file} has human_era_cutoff but no human_era_cited_prs list.")
        cutoff = citations["human_era_cutoff"]
    else:
        cited_prs = citations["cited_prs"]
        cutoff = None

    cited_set = set(cited_prs)

    conn = sqlite3.connect(args.processed_db)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT ce.source_pr_number, ce.occurred_at,
               ps.p_score, ps.is_high_p,
               rs.r_score, rs.is_high_r,
               dv.quadrant
        FROM candidate_events ce
        LEFT JOIN event_p_scores ps ON ps.event_id = ce.id
        LEFT JOIN event_r_scores rs ON rs.event_id = ce.id
        LEFT JOIN event_divergence dv ON dv.event_id = ce.id
        WHERE ce.granularity = 'pr_bundle' AND ce.event_type = 'pull_request'
    """
    params = ()
    if cutoff:
        query += " AND ce.occurred_at <= ?"
        params = (cutoff,)
    rows = conn.execute(query, params).fetchall()

    n = len(rows)
    found_cited = [p for p in cited_prs if any(r["source_pr_number"] == p for r in rows)]
    not_found = sorted(set(cited_prs) - set(found_cited))

    report = {
        "repo": repo,
        "processed_db": args.processed_db,
        "citations_file": args.citations_file,
        "human_era_only": args.human_era_only,
        "era_cutoff_used": cutoff,
        "population_size": n,
        "cited_prs_in_file": len(cited_prs),
        "cited_prs_found_in_collected_data": len(found_cited),
        "cited_prs_not_found": not_found,
        "base_rate": (len(found_cited) / n) if n else None,
        "metrics": {
            "is_high_p": confusion(rows, cited_set, lambda r: bool(r["is_high_p"])),
            "is_high_r": confusion(rows, cited_set, lambda r: bool(r["is_high_r"])),
            "truly_important": confusion(rows, cited_set, lambda r: r["quadrant"] == "truly_important"),
            "high_p_or_high_r": confusion(rows, cited_set, lambda r: bool(r["is_high_p"]) or bool(r["is_high_r"])),
        },
    }

    print(json.dumps(report, indent=2))

    era_tag = "_human_era" if args.human_era_only else ""
    safe_name = repo.replace("/", "__")
    out_path = Path(args.citations_file).parent / f"{safe_name}{era_tag}_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
