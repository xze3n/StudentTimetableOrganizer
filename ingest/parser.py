"""Parse the official UBB tabular timetable pages into Activity records."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .schema import ACTIVITY_TYPES, DAYS, WEEK_PATTERNS, Activity

EXPECTED_HEADER = [
    "Ziua", "Orele", "Frecventa", "Sala", "Formatia", "Tipul", "Disciplina", "Cadrul didactic",
]

LANGUAGES = ("romana", "engleza", "maghiara", "germana")


class ParseError(ValueError):
    """The page does not have the structure we expect."""


@dataclass(frozen=True)
class CohortLink:
    """One cell of the tabular index: a programme and study year with its page."""

    program: str  # full text, e.g. "Informatica - linia de studiu romana"
    specialization: str  # e.g. "Informatica"
    teaching_language: str  # e.g. "romana"
    study_year: int
    cohort_code: str  # page code, e.g. "I1"


def _text(el) -> str:
    return el.get_text(" ", strip=True).replace("\xa0", " ").strip()


def split_program(program: str) -> tuple[str, str]:
    """'Informatica - linia de studiu romana' -> ('Informatica', 'romana')."""
    lowered = program.lower()
    language = next((lang for lang in LANGUAGES if lang in lowered), "romana")
    specialization = re.split(r"\s+-\s+|\s+in limba\s+", program, maxsplit=1)[0].strip()
    return specialization, language


def parse_index(html: str) -> list[CohortLink]:
    """Parse ``tabelar/index.html`` into the list of cohort pages."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[CohortLink] = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        program = _text(cells[0])
        specialization, language = split_program(program)
        for cell in cells[1:]:
            a = cell.find("a")
            if not a:
                continue
            m = re.match(r"Anul\s+(\d)", _text(a))
            code = a.get("href", "").removesuffix(".html")
            if m and code:
                links.append(CohortLink(program, specialization, language, int(m.group(1)), code))
    if not links:
        raise ParseError("no cohort links found in the index page")
    return links


def _hours(text: str) -> tuple[str, str]:
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", text)
    if not m:
        raise ParseError(f"unexpected time range {text!r}")
    start, end = int(m.group(1)), int(m.group(2))
    if not 7 <= start < end <= 22:
        raise ParseError(f"time range out of bounds {text!r}")
    return f"{start:02d}:00", f"{end:02d}:00"


def _formation(formation: str) -> tuple[str | None, str | None]:
    """'211/2' -> ('211', '2'); '211' -> ('211', None); 'I1' -> (None, None)."""
    # Groups are 3 digits for most programmes (211) and 4 for some (1021).
    m = re.fullmatch(r"(\d{3,4})(?:/(\d))?", formation)
    if not m:
        return None, None  # whole cohort, e.g. lectures for "I1"
    return m.group(1), m.group(2)


def parse_cohort_page(
    html: str,
    *,
    academic_year: str,
    semester: int,
    cohort: CohortLink,
    source_url: str,
) -> list[Activity]:
    """Parse one cohort page (one table per group) into de-duplicated activities."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise ParseError("no timetable tables on the page")

    seen: dict[str, Activity] = {}
    for table in tables:
        rows = table.find_all("tr")
        header = [_text(th) for th in rows[0].find_all("th")] if rows else []
        if header != EXPECTED_HEADER:
            raise ParseError(f"unexpected table header {header!r}")
        for row in rows[1:]:
            cells = [_text(td) for td in row.find_all("td")]
            if len(cells) != len(EXPECTED_HEADER):
                raise ParseError(f"row with {len(cells)} cells: {cells!r}")
            day, hours, freq, room, formation, kind, course, teacher = cells

            if day not in DAYS:
                raise ParseError(f"unknown day {day!r}")
            if freq not in WEEK_PATTERNS:
                raise ParseError(f"unknown frequency label {freq!r}")
            if kind not in ACTIVITY_TYPES:
                raise ParseError(f"unknown activity type {kind!r}")
            if not course:
                raise ParseError(f"row without a course name: {cells!r}")

            start, end = _hours(hours)
            group, subgroup = _formation(formation)
            activity = Activity(
                academic_year=academic_year,
                semester=semester,
                cohort_code=cohort.cohort_code,
                specialization=cohort.specialization,
                teaching_language=cohort.teaching_language,
                study_year=cohort.study_year,
                course_name=course,
                activity_type=kind,
                formation=formation,
                group=group,
                subgroup=subgroup,
                day=DAYS[day],
                start_time=start,
                end_time=end,
                room=room,
                teacher=teacher,
                frequency_label=freq,
                week_pattern=WEEK_PATTERNS[freq],
                source_url=source_url,
            )
            seen.setdefault(activity.activity_id, activity)
    return list(seen.values())
