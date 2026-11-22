"""Fetch prototype: download one cohort's official timetable and print its records.

Usage:
    python -m ingest.fetch 2026-2027 1 Informatica romana 1
    python -m ingest.fetch 2026-2027 1 Informatica romana 1 --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable

import requests

from .parser import CohortLink, parse_cohort_page, parse_index
from .schema import Activity
from .urls import cohort_url, index_url

# The official pages declare ISO-8859-2 (Romanian diacritics).
ENCODING = "iso-8859-2"
HEADERS = {"User-Agent": "StudentTimetableOrganizer/0.1 (university project)"}


def get_page(url: str, timeout: float = 15.0) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.content.decode(ENCODING)


def find_cohort(
    links: list[CohortLink], specialization: str, teaching_language: str, study_year: int
) -> CohortLink:
    for link in links:
        if (
            link.specialization.lower() == specialization.lower()
            and link.teaching_language == teaching_language.lower()
            and link.study_year == study_year
        ):
            return link
    available = sorted({f"{l.specialization} ({l.teaching_language})" for l in links})
    raise LookupError(
        f"no timetable for {specialization} / {teaching_language} / year {study_year}; "
        f"available programmes: {', '.join(available)}"
    )


def resolve_cohort(
    academic_year: str,
    semester: int,
    specialization: str,
    teaching_language: str,
    study_year: int,
    *,
    page_getter: Callable[[str], str] = get_page,
) -> CohortLink:
    links = parse_index(page_getter(index_url(academic_year, semester)))
    return find_cohort(links, specialization, teaching_language, study_year)


def fetch_cohort(
    academic_year: str,
    semester: int,
    cohort: CohortLink,
    *,
    page_getter: Callable[[str], str] = get_page,
) -> tuple[str, list[Activity]]:
    """Fetch and parse one cohort page; returns (source URL, activities)."""
    url = cohort_url(academic_year, semester, cohort.cohort_code)
    activities = parse_cohort_page(
        page_getter(url), academic_year=academic_year, semester=semester, cohort=cohort, source_url=url
    )
    return url, activities


def fetch_timetable(
    academic_year: str, semester: int, specialization: str, teaching_language: str, study_year: int
) -> list[Activity]:
    cohort = resolve_cohort(academic_year, semester, specialization, teaching_language, study_year)
    return fetch_cohort(academic_year, semester, cohort)[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("academic_year")
    ap.add_argument("semester", type=int)
    ap.add_argument("specialization")
    ap.add_argument("teaching_language")
    ap.add_argument("study_year", type=int)
    ap.add_argument("--json", help="write the records to this JSON file")
    args = ap.parse_args(argv)

    activities = fetch_timetable(
        args.academic_year, args.semester, args.specialization, args.teaching_language, args.study_year
    )
    print(f"{len(activities)} activities from {activities[0].source_url if activities else '-'}")
    print("by type:", dict(Counter(a.activity_type for a in activities)))
    print("by week pattern:", dict(Counter(a.week_pattern for a in activities)))
    print("groups:", sorted({a.group for a in activities if a.group}))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([a.to_dict() for a in activities], f, ensure_ascii=False, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
