"""Semester-wide data checks on parsed timetable records.

    python -m ingest.check 2026-2027 1             # every cohort page of the semester
    python -m ingest.check 2026-2027 1 --only I1 IA2

The parser already rejects malformed rows. These checks look at the records
as a whole: how complete the fields are, and suspicious duplicates or
overlaps that the solver would have to deal with.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .fetch import fetch_cohort, get_page
from .parser import parse_index
from .schema import Activity
from .urls import index_url

REQUIRED = ["course_name", "activity_type", "formation", "day", "start_time", "end_time", "room", "teacher"]


@dataclass
class ValidationReport:
    total: int = 0
    missing: Counter = field(default_factory=Counter)  # field -> number of records missing it
    duplicates: list[tuple[Activity, Activity]] = field(default_factory=list)
    overlaps: list[tuple[Activity, Activity]] = field(default_factory=list)

    def coverage(self, name: str) -> float:
        return 1.0 if not self.total else 1 - self.missing[name] / self.total


def weeks_overlap(a: str, b: str) -> bool:
    return a == "all" or b == "all" or a == b


def times_overlap(a: Activity, b: Activity) -> bool:
    return a.day == b.day and a.start_time < b.end_time and b.start_time < a.end_time


def audience(a: Activity) -> tuple:
    """Who attends: the whole cohort, a group, or a half-group."""
    return (a.cohort_code, a.group, a.subgroup)


def attends_both(a: Activity, b: Activity) -> bool:
    """True when some student is expected at both activities."""
    if a.cohort_code != b.cohort_code:
        return False
    if a.group is None or b.group is None:  # whole-cohort activity
        return True
    if a.group != b.group:
        return False
    return a.subgroup is None or b.subgroup is None or a.subgroup == b.subgroup


def validate_activities(activities: list[Activity]) -> ValidationReport:
    report = ValidationReport(total=len(activities))
    for a in activities:
        for name in REQUIRED:
            if not getattr(a, name):
                report.missing[name] += 1

    # Same course, type, audience and time slot published twice with different details.
    by_slot = defaultdict(list)
    for a in activities:
        by_slot[(audience(a), a.course_name, a.activity_type, a.day, a.start_time, a.week_pattern)].append(a)
    for same in by_slot.values():
        report.duplicates += [(same[0], other) for other in same[1:]]

    # Two different activities the same students are expected to attend at once.
    by_cohort_day = defaultdict(list)
    for a in activities:
        by_cohort_day[(a.cohort_code, a.day)].append(a)
    for day_acts in by_cohort_day.values():
        day_acts.sort(key=lambda x: x.start_time)
        for i, a in enumerate(day_acts):
            for b in day_acts[i + 1:]:
                if b.start_time >= a.end_time:
                    break
                if (
                    a.course_name != b.course_name
                    and attends_both(a, b)
                    and times_overlap(a, b)
                    and weeks_overlap(a.week_pattern, b.week_pattern)
                ):
                    report.overlaps.append((a, b))
    return report


def _fmt(a: Activity) -> str:
    return f"{a.cohort_code} {a.formation} {a.day} {a.start_time}-{a.end_time} {a.activity_type} {a.course_name} ({a.week_pattern})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("academic_year")
    ap.add_argument("semester", type=int)
    ap.add_argument("--only", nargs="*", help="cohort codes to check (default: all)")
    ap.add_argument("--show", type=int, default=10, help="how many examples to print per finding")
    args = ap.parse_args(argv)

    links = parse_index(get_page(index_url(args.academic_year, args.semester)))
    if args.only:
        links = [l for l in links if l.cohort_code in set(args.only)]

    activities: list[Activity] = []
    failures = []
    for link in links:
        try:
            activities += fetch_cohort(args.academic_year, args.semester, link)[1]
        except Exception as exc:
            failures.append((link.cohort_code, f"{type(exc).__name__}: {exc}"))

    report = validate_activities(activities)
    print(f"Cohort pages: {len(links) - len(failures)}/{len(links)} parsed")
    for code, err in failures:
        print(f"  FAILED {code}: {err}")
    print(f"Activities: {report.total}")
    print(f"Week patterns: {dict(Counter(a.week_pattern for a in activities))}")
    print("Required-field coverage:")
    for name in REQUIRED:
        print(f"  {name:14} {report.coverage(name):7.2%}  ({report.missing[name]} missing)")
    print(f"Duplicate publications: {len(report.duplicates)}")
    for a, b in report.duplicates[: args.show]:
        print(f"  {_fmt(a)}  | room {a.room}/{b.room}, teacher {a.teacher} / {b.teacher}")
    print(f"Overlaps for the same students: {len(report.overlaps)}")
    for a, b in report.overlaps[: args.show]:
        print(f"  {_fmt(a)}\n    x {_fmt(b)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
