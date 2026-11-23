"""Parse the official UBB tabular timetable pages into Activity records."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .matching import normalize
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
    teaching_language: str  # e.g. "romana" or "germana si engleza"
    study_year: int
    cohort_code: str  # page code, e.g. "I1"


def _text(el) -> str:
    return el.get_text(" ", strip=True).replace("\xa0", " ").strip()


def split_program(program: str) -> tuple[str, str]:
    """'Informatica - linia de studiu romana' -> ('Informatica', 'romana')."""
    plain = normalize(program)
    found = sorted((lang for lang in LANGUAGES if lang in plain), key=plain.index)
    language = " si ".join(found) or "romana"
    specialization = re.split(r"\s+-\s+|\s+[iî]n limba\s+", program, maxsplit=1)[0].strip()
    return specialization, language


def _check_complete(html: str) -> None:
    if not re.search(r"</html\s*>", html, re.IGNORECASE):
        raise ParseError("page is incomplete: no closing </html> tag")


def parse_index(html: str) -> list[CohortLink]:
    """Parse ``tabelar/index.html`` into the list of cohort pages."""
    _check_complete(html)
    soup = BeautifulSoup(html, "html.parser")
    links: list[CohortLink] = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        program = _text(cells[0])
        specialization, language = split_program(program)
        for cell in cells[1:]:
            for a in cell.find_all("a"):
                label, href = _text(a), a.get("href", "")
                m = re.match(r"Anul\s+([0-9])", label)
                code = href.removesuffix(".html")
                if not m or not code:
                    raise ParseError(f"unexpected index link {label!r} ({href!r}) for {program!r}")
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


def _formation(formation: str, cohort_code: str) -> tuple[str | None, str | None]:
    """'211/2' -> ('211', '2'); '211' -> ('211', None); 'I1' -> (None, None)."""
    # Groups are 3 digits for most programmes (211) and 4 for some (1021).
    if formation == cohort_code:
        return None, None  # whole cohort, e.g. lectures for "I1"
    m = re.fullmatch(r"([0-9]{3,4})(?:/([0-9]))?", formation)
    if not m:
        raise ParseError(f"unknown formation {formation!r} on the page of {cohort_code}")
    return m.group(1), m.group(2)


def parse_cohort_page(
    html: str,
    *,
    academic_year: str,
    semester: int,
    cohort: CohortLink,
    source_url: str,
) -> list[Activity]:
    """Parse one cohort page (one table per group) into de-duplicated activities.

    Returns [] when no classes are published. The site does this in two ways:
    group tables without rows, or just the "Orar Anul N" title without groups.
    """
    _check_complete(html)
    soup = BeautifulSoup(html, "html.parser")
    headings = [_text(h) for h in soup.find_all("h1")]
    group_count = sum(h.startswith("Grupa") for h in headings)
    tables = soup.find_all("table")
    if len(tables) != group_count:
        raise ParseError(f"{group_count} group headings but {len(tables)} tables")
    if not tables:
        if any(h.startswith("Orar Anul") for h in headings):
            return []
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
            group, subgroup = _formation(formation, cohort.cohort_code)
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
