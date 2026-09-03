"""File identity tracking across renames (Stage 2).

`commit_files` records each file change under whatever path it had *at
that commit* — a file renamed twice looks like three unrelated paths with
no link between them. This assigns every observed path a stable
`file_id` that survives renames, which later R-feature work (file
survival, module survival — CLAUDE.md Section 2/24) needs: "is the file
this event touched still present" is meaningless without knowing a
renamed file is still the same file.

Commits are walked in `author_date_utc` order (the UTC-normalized column —
see schema.py's comment on why plain `author_date` isn't safe to sort by:
it keeps each committer's original local offset, which does not sort
correctly against other offsets as text) as a proxy for true chronological
order. This is a documented simplification, not a proven-correct ordering:
even correctly-sorted timestamps can be out of step with actual merge
order for rebased or cherry-picked commits. Revisit if that turns out to
matter for a given repository's history.

On DELETE, the path is retired from the active mapping — a later ADD at
the same path is treated as a *new* file identity, not a resurrection of
the old one. This matches how Git itself treats it (a deletion breaks the
rename-detection chain) rather than assuming path reuse implies identity.
"""

from dataclasses import dataclass, field
from sqlite3 import Connection


@dataclass
class FilePathObservation:
    commit_hash: str
    path: str
    change_type: str


@dataclass
class FileIdentityRecord:
    first_path: str
    last_path: str
    is_deleted: bool = False
    path_history: list[FilePathObservation] = field(default_factory=list)


def build_file_identities(raw_conn: Connection) -> list[FileIdentityRecord]:
    rows = raw_conn.execute(
        """
        SELECT c.hash, c.author_date_utc, cf.filename, cf.old_path, cf.change_type
        FROM commits c
        JOIN commit_files cf ON cf.repo_id = c.repo_id AND cf.commit_hash = c.hash
        WHERE cf.filename IS NOT NULL
        ORDER BY c.author_date_utc ASC, c.hash ASC, cf.id ASC
        """
    ).fetchall()

    files: list[FileIdentityRecord] = []
    active_path_to_index: dict[str, int] = {}

    def touch(index: int, commit_hash: str, path: str, change_type: str) -> None:
        files[index].last_path = path
        files[index].path_history.append(FilePathObservation(commit_hash, path, change_type))

    for commit_hash, _author_date, path, old_path, change_type in rows:
        if change_type == "RENAME" and old_path:
            if old_path in active_path_to_index:
                index = active_path_to_index.pop(old_path)
            else:
                # Renamed from a path we never saw an ADD/MODIFY for
                # (e.g. present at the very first collected commit, or a
                # gap from --branch-restricted collection) — start a new
                # identity here rather than losing the observation.
                index = len(files)
                files.append(FileIdentityRecord(first_path=old_path, last_path=old_path))
            active_path_to_index[path] = index
            touch(index, commit_hash, path, change_type)
            continue

        if change_type == "DELETE":
            if path in active_path_to_index:
                index = active_path_to_index.pop(path)
            else:
                index = len(files)
                files.append(FileIdentityRecord(first_path=path, last_path=path))
            files[index].is_deleted = True
            touch(index, commit_hash, path, change_type)
            continue

        # ADD, MODIFY, COPY, or UNKNOWN: same file identity if we've seen
        # this exact path before and it's still active, else a new one.
        if path in active_path_to_index:
            index = active_path_to_index[path]
        else:
            index = len(files)
            files.append(FileIdentityRecord(first_path=path, last_path=path))
            active_path_to_index[path] = index
        files[index].is_deleted = False
        touch(index, commit_hash, path, change_type)

    return files
