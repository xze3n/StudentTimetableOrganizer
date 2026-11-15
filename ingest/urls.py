"""Build official UBB timetable URLs from an academic year and semester.

URLs are only ever built here, from validated arguments, so the model can
never point the fetcher at an arbitrary address.
"""

from __future__ import annotations

import re

BASE_URL = "https://www.cs.ubbcluj.ro/files/orar"

_ACADEMIC_YEAR = re.compile(r"^(\d{4})-(\d{4})$")
_COHORT_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,30}$")


def semester_folder(academic_year: str, semester: int) -> str:
    """'2026-2027', 1 -> '2026-1' (the folder name used by the faculty)."""
    m = _ACADEMIC_YEAR.match(academic_year)
    if not m or int(m.group(2)) != int(m.group(1)) + 1:
        raise ValueError(f"academic year must look like '2026-2027', got {academic_year!r}")
    if semester not in (1, 2):
        raise ValueError(f"semester must be 1 or 2, got {semester!r}")
    start = int(m.group(1))
    if start < 2014:
        raise ValueError("official timetables are only available from 2014 onwards")
    return f"{start}-{semester}"


def index_url(academic_year: str, semester: int) -> str:
    """URL of the tabular index listing every cohort page."""
    return f"{BASE_URL}/{semester_folder(academic_year, semester)}/tabelar/index.html"


def cohort_url(academic_year: str, semester: int, cohort_code: str) -> str:
    """URL of one cohort page, e.g. code 'I1' = Informatica, Romanian, year 1."""
    if not _COHORT_CODE.match(cohort_code):
        raise ValueError(f"invalid cohort code {cohort_code!r}")
    return f"{BASE_URL}/{semester_folder(academic_year, semester)}/tabelar/{cohort_code}.html"
