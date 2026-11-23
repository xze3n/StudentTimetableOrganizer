"""SQLite cache of official timetable snapshots.

Each successful fetch of a non-empty cohort page produces a *snapshot*: the full
set of activity records plus where and when they were fetched. Old snapshots are
kept; one snapshot per student context (academic year, semester, specialization,
language, study year) is active, and at most one per page code.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

from .matching import best_match, context_key
from .schema import Activity

ACTIVITY_FIELDS = [f.name for f in fields(Activity)]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id       TEXT PRIMARY KEY,
    academic_year     TEXT NOT NULL,
    semester          INTEGER NOT NULL,
    cohort_code       TEXT NOT NULL,
    specialization    TEXT NOT NULL,
    teaching_language TEXT NOT NULL,
    study_year        INTEGER NOT NULL,
    source_url        TEXT NOT NULL,
    fetched_at        TEXT NOT NULL,
    checked_at        TEXT NOT NULL,
    record_count      INTEGER NOT NULL,
    content_hash      TEXT NOT NULL,
    is_active         INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_snapshot
    ON snapshots (academic_year, semester, cohort_code) WHERE is_active = 1;

CREATE TABLE IF NOT EXISTS activities (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    activity_id TEXT NOT NULL,
    {{activity_columns}},
    PRIMARY KEY (snapshot_id, activity_id)
);
CREATE INDEX IF NOT EXISTS activities_by_group ON activities (snapshot_id, "group");
""".replace(
    "{activity_columns}",
    ", ".join(
        f'"{name}" {"INTEGER" if name in ("semester", "study_year") else "TEXT"}' for name in ACTIVITY_FIELDS
    ),
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def content_hash(activities: list[Activity]) -> str:
    """Hash of every field, including metadata that is not part of activity_id."""
    records = sorted(json.dumps(a.to_dict(), sort_keys=True) for a in activities)
    return hashlib.sha1("\n".join(records).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    academic_year: str
    semester: int
    cohort_code: str
    specialization: str
    teaching_language: str
    study_year: int
    source_url: str
    fetched_at: str
    checked_at: str
    record_count: int
    content_hash: str
    is_active: bool


@dataclass(frozen=True)
class SnapshotDiff:
    added: list[Activity]
    removed: list[Activity]
    changed: list[tuple[Activity, Activity]]  # (old, new): same activity, moved or reassigned

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def summary(self) -> str:
        return f"{len(self.added)} added, {len(self.removed)} removed, {len(self.changed)} changed"


def _q(name: str) -> str:
    return f'"{name}"'  # "group" is an SQL keyword


class TimetableStore:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- snapshots ----------------------------------------------------------

    def active_snapshot(self, academic_year: str, semester: int, cohort_code: str) -> Snapshot | None:
        row = self.conn.execute(
            "SELECT * FROM snapshots WHERE academic_year=? AND semester=? AND cohort_code=? AND is_active=1",
            (academic_year, semester, cohort_code),
        ).fetchone()
        return self._snapshot(row) if row else None

    def find_active(
        self, academic_year: str, semester: int, specialization: str, teaching_language: str, study_year: int
    ) -> Snapshot | None:
        """Active snapshot for a student context, without knowing the page code."""
        active = self._active_in_semester(academic_year, semester)
        return best_match(active, specialization, teaching_language, study_year)

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        row = self.conn.execute("SELECT * FROM snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        return self._snapshot(row) if row else None

    def list_snapshots(self, academic_year: str, semester: int, cohort_code: str) -> list[Snapshot]:
        rows = self.conn.execute(
            "SELECT * FROM snapshots WHERE academic_year=? AND semester=? AND cohort_code=? "
            "ORDER BY fetched_at, rowid",
            (academic_year, semester, cohort_code),
        ).fetchall()
        return [self._snapshot(r) for r in rows]

    def save_snapshot(
        self, activities: list[Activity], *, source_url: str, fetched_at: str | None = None
    ) -> Snapshot:
        """Store a complete, already-validated set of records and make it active.

        It replaces the active snapshot of the same student context, even if the
        page code changed, and of the same page code, even if the context changed.

        Runs in one transaction: if anything fails, the previous active
        snapshot stays active and nothing partial is written.
        """
        if not activities:
            raise ValueError("refusing to store an empty snapshot")
        first = activities[0]
        key = (first.academic_year, first.semester, first.cohort_code)
        if any((a.academic_year, a.semester, a.cohort_code) != key for a in activities):
            raise ValueError("all activities in a snapshot must belong to the same cohort and semester")
        if len({a.activity_id for a in activities}) != len(activities):
            raise ValueError("duplicate activity IDs in snapshot")

        fetched_at = fetched_at or now_utc()
        digest = content_hash(activities)
        stamp = fetched_at.replace("-", "").replace(":", "")[:15]
        # The random suffix keeps IDs unique when identical data is saved twice in one second.
        snapshot_id = (
            f"{first.academic_year[:4]}-{first.semester}-{first.cohort_code}-"
            f"{stamp}-{digest[:6]}-{secrets.token_hex(4)}"
        )
        context = context_key(first.specialization, first.teaching_language, first.study_year)
        replaced = [
            (s.snapshot_id,)
            for s in self._active_in_semester(first.academic_year, first.semester)
            if s.cohort_code == first.cohort_code
            or context_key(s.specialization, s.teaching_language, s.study_year) == context
        ]

        cols = ["snapshot_id", "activity_id", *ACTIVITY_FIELDS]
        insert = (
            f"INSERT INTO activities ({', '.join(map(_q, cols))}) "
            f"VALUES ({', '.join('?' for _ in cols)})"
        )
        with self.conn:
            self.conn.executemany("UPDATE snapshots SET is_active=0 WHERE snapshot_id=?", replaced)
            self.conn.execute(
                "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                (
                    snapshot_id, first.academic_year, first.semester, first.cohort_code,
                    first.specialization, first.teaching_language, first.study_year,
                    source_url, fetched_at, fetched_at, len(activities), digest,
                ),
            )
            self.conn.executemany(
                insert,
                [(snapshot_id, a.activity_id, *(getattr(a, n) for n in ACTIVITY_FIELDS)) for a in activities],
            )
        return self.get_snapshot(snapshot_id)

    def _active_in_semester(self, academic_year: str, semester: int) -> list[Snapshot]:
        """Active snapshots of one semester, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM snapshots WHERE academic_year=? AND semester=? AND is_active=1 "
            "ORDER BY fetched_at DESC, rowid DESC",
            (academic_year, semester),
        ).fetchall()
        return [self._snapshot(r) for r in rows]

    # --- activities ---------------------------------------------------------

    def load_activities(self, snapshot_id: str) -> list[Activity]:
        rows = self.conn.execute(
            f"SELECT {', '.join(map(_q, ACTIVITY_FIELDS))} FROM activities WHERE snapshot_id=? "
            "ORDER BY day, start_time, formation",
            (snapshot_id,),
        ).fetchall()
        return [Activity(**dict(r)) for r in rows]

    def diff(self, old_snapshot_id: str, new_snapshot_id: str) -> SnapshotDiff:
        return diff_activities(self.load_activities(old_snapshot_id), self.load_activities(new_snapshot_id))

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> Snapshot:
        d = dict(row)
        d["is_active"] = bool(d["is_active"])
        return Snapshot(**d)


def diff_activities(old: list[Activity], new: list[Activity]) -> SnapshotDiff:
    """Compare two snapshots of the same cohort.

    Records with the same published details are unchanged, even if the page code
    differs. Among the rest, an old and a new record of the same course, activity
    type and audience can form one *changed* activity (moved in time or room, or
    new teacher). The most similar records are paired first; anything left over
    is added or removed.
    """

    def ident(a: Activity) -> tuple:
        # A whole-cohort formation is the page code, which can be renamed.
        formation = "" if a.formation == a.cohort_code else a.formation
        return (formation, a.activity_type, a.course_name)

    def slot(a: Activity) -> tuple:
        return (a.day, a.start_time, a.end_time)

    def details(a: Activity) -> tuple:
        return (*ident(a), *slot(a), a.room, a.teacher, a.frequency_label)

    def similarity(a: Activity, b: Activity) -> tuple[int, bool]:
        same_slot = slot(a) == slot(b)
        same = [same_slot, a.room == b.room, a.teacher == b.teacher, a.frequency_label == b.frequency_label]
        return sum(same), same_slot  # on a tie, prefer the one in the same slot

    old_details = {details(a) for a in old}
    new_details = {details(a) for a in new}
    gone = sorted((a for a in old if details(a) not in new_details), key=details)
    came = sorted((b for b in new if details(b) not in old_details), key=details)

    candidates = [(a, b) for a in gone for b in came if ident(a) == ident(b)]
    candidates.sort(key=lambda pair: similarity(*pair), reverse=True)

    changed: list[tuple[Activity, Activity]] = []
    for a, b in candidates:
        if a in gone and b in came:
            gone.remove(a)
            came.remove(b)
            changed.append((a, b))
    return SnapshotDiff(added=came, removed=gone, changed=changed)
