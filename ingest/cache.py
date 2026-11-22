"""Cached access to the official timetable, with explicit refresh.

    python -m ingest.cache 2026-2027 1 Informatica romana 1            # use cache, fetch if missing
    python -m ingest.cache 2026-2027 1 Informatica romana 1 --refresh  # re-fetch and show the diff
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .fetch import fetch_cohort, get_page, resolve_cohort
from .schema import Activity
from .store import Snapshot, SnapshotDiff, TimetableStore, content_hash, now_utc

DEFAULT_DB = Path("data") / "timetable.sqlite"


@dataclass(frozen=True)
class CacheResult:
    status: str  # "cached" | "fetched" | "updated" | "unchanged" | "fallback"
    snapshot: Snapshot
    activities: list[Activity]
    diff: SnapshotDiff | None = None  # set when a refresh changed the data
    error: str | None = None  # set on fallback: why the fetch failed

    def describe(self) -> str:
        s = self.snapshot
        base = f"{s.record_count} activities, snapshot {s.snapshot_id} (fetched {s.fetched_at})"
        if self.status == "fallback":
            return f"Could not fetch the official timetable ({self.error}); using cached {base}."
        if self.status == "updated" and self.diff is not None:
            return f"Timetable updated: {self.diff.summary()}. Now {base}."
        if self.status == "unchanged":
            return f"Timetable unchanged since last fetch; {base}, checked {s.checked_at}."
        return f"{self.status.capitalize()}: {base}."


def get_timetable(
    store: TimetableStore,
    academic_year: str,
    semester: int,
    specialization: str,
    teaching_language: str,
    study_year: int,
    *,
    refresh: bool = False,
    page_getter: Callable[[str], str] = get_page,
) -> CacheResult:
    """Return the active snapshot for a cohort, fetching it when needed.

    - No refresh and a cached snapshot exists: return it without network access.
    - Otherwise fetch and parse. The active snapshot is only replaced once the
      new data has parsed and validated; identical data just updates checked_at.
    - If fetching or parsing fails and a cached snapshot exists, fall back to it
      and report the error; with no cache, the error is raised.
    """
    current = store.find_active(academic_year, semester, specialization, teaching_language, study_year)
    if current and not refresh:
        return CacheResult("cached", current, store.load_activities(current.snapshot_id))

    try:
        cohort = resolve_cohort(
            academic_year, semester, specialization, teaching_language, study_year,
            page_getter=page_getter,
        )
        url, activities = fetch_cohort(academic_year, semester, cohort, page_getter=page_getter)
    except LookupError:
        raise  # the programme/year does not exist: not a fetch failure
    except Exception as exc:  # network error, changed layout, invalid data
        if current is None:
            raise
        return CacheResult(
            "fallback", current, store.load_activities(current.snapshot_id),
            error=f"{type(exc).__name__}: {exc}",
        )

    if current and content_hash(activities) == current.content_hash:
        store.mark_checked(current.snapshot_id)
        current = store.get_snapshot(current.snapshot_id)
        return CacheResult("unchanged", current, store.load_activities(current.snapshot_id))

    new = store.save_snapshot(activities, source_url=url, fetched_at=now_utc())
    if current is None:
        return CacheResult("fetched", new, store.load_activities(new.snapshot_id))
    return CacheResult(
        "updated", new, store.load_activities(new.snapshot_id),
        diff=store.diff(current.snapshot_id, new.snapshot_id),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("academic_year")
    ap.add_argument("semester", type=int)
    ap.add_argument("specialization")
    ap.add_argument("teaching_language")
    ap.add_argument("study_year", type=int)
    ap.add_argument("--refresh", action="store_true", help="re-fetch from the official site")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args(argv)

    store = TimetableStore(args.db)
    try:
        result = get_timetable(
            store, args.academic_year, args.semester, args.specialization,
            args.teaching_language, args.study_year, refresh=args.refresh,
        )
    finally:
        store.close()
    print(result.describe())
    if result.diff and not result.diff.is_empty:
        for a in result.diff.added:
            print(f"  + {a.course_name} ({a.activity_type}, {a.formation}) {a.day} {a.start_time}, {a.room}")
        for a in result.diff.removed:
            print(f"  - {a.course_name} ({a.activity_type}, {a.formation}) {a.day} {a.start_time}, {a.room}")
        for old, new in result.diff.changed:
            print(
                f"  ~ {new.course_name} ({new.activity_type}, {new.formation}): "
                f"{old.day} {old.start_time} {old.room} -> {new.day} {new.start_time} {new.room}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
