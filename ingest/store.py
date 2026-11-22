"""SQLite cache of official timetable snapshots.

Each fetch of one cohort page produces a *snapshot*: the full set of activity
records plus where and when they were fetched. Old snapshots are kept; exactly
one snapshot per (academic year, semester, cohort) is active.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

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
    ids = sorted(a.activity_id for a in activities)
    return hashlib.sha1("\n".join(ids).encode()).hexdigest()[:12]


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
        row = self.conn.execute(
            "SELECT * FROM snapshots WHERE academic_year=? AND semester=? AND lower(specialization)=lower(?) "
            "AND teaching_language=lower(?) AND study_year=? AND is_active=1",
            (academic_year, semester, specialization, teaching_language, study_year),
        ).fetchone()
        return self._snapshot(row) if row else None

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        row = self.conn.execute("SELECT * FROM snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        return self._snapshot(row) if row else None

    def list_snapshots(self, academic_year: str, semester: int, cohort_code: str) -> list[Snapshot]:
        rows = self.conn.execute(
            "SELECT * FROM snapshots WHERE academic_year=? AND semester=? AND cohort_code=? ORDER BY fetched_at",
            (academic_year, semester, cohort_code),
        ).fetchall()
        return [self._snapshot(r) for r in rows]

    def save_snapshot(
        self, activities: list[Activity], *, source_url: str, fetched_at: str | None = None
    ) -> Snapshot:
        """Store a complete, already-validated set of records and make it active.

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
        snapshot_id = f"{first.academic_year[:4]}-{first.semester}-{first.cohort_code}-{stamp}-{digest[:6]}"

        cols = ["snapshot_id", "activity_id", *ACTIVITY_FIELDS]
        insert = (
            f"INSERT INTO activities ({', '.join(map(_q, cols))}) "
            f"VALUES ({', '.join('?' for _ in cols)})"
        )
        with self.conn:
            self.conn.execute(
                "UPDATE snapshots SET is_active=0 WHERE academic_year=? AND semester=? AND cohort_code=?", key
            )
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

    def mark_checked(self, snapshot_id: str, checked_at: str | None = None) -> None:
        """Record that the source was re-checked and had not changed."""
        with self.conn:
            self.conn.execute(
                "UPDATE snapshots SET checked_at=? WHERE snapshot_id=?", (checked_at or now_utc(), snapshot_id)
            )

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

    Records present in both are unchanged. Among the rest, an old and a new
    record of the same course, activity type and formation are reported as
    one *changed* activity (moved in time or room, or new teacher); anything
    left over is added or removed.
    """
    old_ids = {a.activity_id for a in old}
    new_ids = {a.activity_id for a in new}
    gone = [a for a in old if a.activity_id not in new_ids]
    came = [a for a in new if a.activity_id not in old_ids]

    def ident(a: Activity) -> tuple:
        return (a.formation, a.activity_type, a.course_name)

    def order(a: Activity) -> tuple:
        return (a.day, a.start_time, a.room)

    changed: list[tuple[Activity, Activity]] = []
    removed: list[Activity] = []
    remaining = sorted(came, key=order)
    for a in sorted(gone, key=order):
        match = next((b for b in remaining if ident(b) == ident(a)), None)
        if match is None:
            removed.append(a)
        else:
            remaining.remove(match)
            changed.append((a, match))
    return SnapshotDiff(added=remaining, removed=removed, changed=changed)
