"""Parser tests on saved copies of the official 2026-2027 semester I pages."""

import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from ingest.fetch import find_cohort
from ingest.parser import ParseError, parse_cohort_page, parse_index, split_program
from ingest.urls import cohort_url, index_url, semester_folder

FIXTURES = Path(__file__).parent / "fixtures" / "2026-1"
SOURCE = "https://www.cs.ubbcluj.ro/files/orar/2026-1/tabelar/I1.html"


def read(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("iso-8859-2")


@pytest.fixture(scope="module")
def links():
    return parse_index(read("index.html"))


@pytest.fixture(scope="module")
def i1(links):
    cohort = find_cohort(links, "Informatica", "romana", 1)
    return parse_cohort_page(
        read("I1.html"), academic_year="2026-2027", semester=1, cohort=cohort, source_url=SOURCE
    )


# --- URLs -------------------------------------------------------------------


def test_semester_folder():
    assert semester_folder("2026-2027", 1) == "2026-1"
    assert semester_folder("2025-2026", 2) == "2025-2"


@pytest.mark.parametrize(
    "year, semester",
    [("2026", 1), ("2026-2028", 1), ("2026-2027", 3), ("2013-2014", 1)],
)
def test_semester_folder_rejects_invalid(year, semester):
    with pytest.raises(ValueError):
        semester_folder(year, semester)


def test_urls():
    assert index_url("2026-2027", 1) == "https://www.cs.ubbcluj.ro/files/orar/2026-1/tabelar/index.html"
    assert cohort_url("2026-2027", 1, "I1") == SOURCE
    assert cohort_url("2026-2027", 1, "MaAI4CI1").endswith("/MaAI4CI1.html")


@pytest.mark.parametrize("code", ["../I1", "I1.html", "http://x", ""])
def test_cohort_url_rejects_unsafe_codes(code):
    with pytest.raises(ValueError):
        cohort_url("2026-2027", 1, code)


# --- Index ------------------------------------------------------------------


def test_split_program():
    assert split_program("Informatica - linia de studiu romana") == ("Informatica", "romana")
    assert split_program("Informatica - in limba engleza") == ("Informatica", "engleza")
    assert split_program("Ingineria Informatiei in limba maghiara") == ("Ingineria Informatiei", "maghiara")


def test_index_lists_cohorts(links):
    codes = {link.cohort_code for link in links}
    assert {"I1", "I2", "I3", "IE1", "IM1", "IG1"} <= codes
    i1 = find_cohort(links, "informatica", "romana", 1)
    assert i1.cohort_code == "I1"


def test_find_cohort_unknown(links):
    with pytest.raises(LookupError):
        find_cohort(links, "Informatica", "romana", 5)


# --- Cohort page ------------------------------------------------------------


def test_counts(i1):
    # 108 published rows; lectures are repeated in all six group tables.
    assert len(i1) == 63
    assert Counter(a.activity_type for a in i1) == {"Curs": 7, "Seminar": 31, "Laborator": 25}
    assert sorted({a.group for a in i1 if a.group}) == ["211", "212", "213", "214", "215", "216"]


def test_lectures_are_whole_cohort(i1):
    for a in i1:
        if a.activity_type == "Curs":
            assert a.formation == "I1"
            assert a.group is None and a.subgroup is None


def test_subgroup_lab(i1):
    [lab] = [
        a for a in i1
        if a.day == "Monday" and a.start_time == "18:00" and a.formation == "211/2"
    ]
    assert lab.group == "211" and lab.subgroup == "2"
    assert lab.activity_type == "Laborator"
    assert lab.course_name == "Arhitectura sistemelor de calcul"
    assert lab.room == "L002"
    assert lab.end_time == "20:00"
    assert lab.week_pattern == "all"


def test_odd_and_even_weeks(i1):
    assert Counter(a.week_pattern for a in i1) == {"all": 57, "odd": 4, "even": 2}
    odd = [a for a in i1 if a.frequency_label == "sapt. 1"]
    assert all(a.week_pattern == "odd" for a in odd)
    assert any(
        a.day == "Wednesday" and a.start_time == "08:00" and a.formation == "211"
        and a.teacher == "Drd. BOTA Daniel"
        for a in odd
    )
    assert all(a.week_pattern == "even" for a in i1 if a.frequency_label == "sapt. 2")


def test_required_fields_present(i1):
    for a in i1:
        assert a.course_name and a.room and a.teacher and a.source_url == SOURCE
        assert a.start_time < a.end_time
        assert a.specialization == "Informatica" and a.teaching_language == "romana"
        assert a.study_year == 1


def test_ids_unique(i1):
    assert len({a.activity_id for a in i1}) == len(i1)


def test_unknown_frequency_label_is_rejected(links):
    html = read("I1.html").replace("sapt. 1", "sapt. 3", 1)
    cohort = find_cohort(links, "Informatica", "romana", 1)
    with pytest.raises(ParseError):
        parse_cohort_page(html, academic_year="2026-2027", semester=1, cohort=cohort, source_url=SOURCE)


def test_changed_layout_is_rejected(links):
    html = read("I1.html").replace("<th>Sala</th>", "<th>Locatie</th>")
    cohort = find_cohort(links, "Informatica", "romana", 1)
    with pytest.raises(ParseError):
        parse_cohort_page(html, academic_year="2026-2027", semester=1, cohort=cohort, source_url=SOURCE)


# --- Incomplete, empty and unexpected pages -----------------------------------


def parse_i1(links, html):
    cohort = find_cohort(links, "Informatica", "romana", 1)
    return parse_cohort_page(html, academic_year="2026-2027", semester=1, cohort=cohort, source_url=SOURCE)


@pytest.mark.parametrize("formation", ["211/A", "211-1", "212 + 213", "I2", ""])
def test_unknown_formation_is_rejected(links, formation):
    html = read("I1.html").replace("211/2", formation)
    with pytest.raises(ParseError, match="formation"):
        parse_i1(links, html)


@pytest.mark.parametrize("marker", ["</table>", "</html>"])
def test_truncated_page_is_rejected(links, marker):
    html = read("I1.html")
    with pytest.raises(ParseError):
        parse_i1(links, html[: html.index(marker)])


def test_group_without_table_is_rejected(links):
    html = re.sub(r"<table.*?</table>", "", read("I1.html"), count=1, flags=re.DOTALL)
    with pytest.raises(ParseError, match="group headings"):
        parse_i1(links, html)


@pytest.mark.parametrize("name", ["2026-1/StEduID1.html", "2025-1/PDAE1.html"])
def test_empty_timetable_has_no_activities(links, name):
    html = (FIXTURES.parent / name).read_bytes().decode("iso-8859-2")
    assert parse_i1(links, html) == []


def test_page_without_timetable_is_rejected(links):
    with pytest.raises(ParseError, match="no timetable tables"):
        parse_i1(links, "<html><body><h1>Site in lucru</h1></body></html>")


def test_unreadable_index_link_is_rejected():
    html = read("index.html").replace('<a href="I1.html" >Anul 1</a>', '<a href="I1.html" >Anul I</a>')
    with pytest.raises(ParseError, match="Anul I"):
        parse_index(html)


def test_every_link_in_an_index_cell_is_read():
    link = '<a href="I1.html" >Anul 1</a>'
    html = read("index.html").replace(link, link + '<a href="IX4.html" >Anul 4</a>')
    assert "IX4" in {c.cohort_code for c in parse_index(html)}


def test_truncated_index_is_rejected():
    html = read("index.html")
    with pytest.raises(ParseError, match="incomplete"):
        parse_index(html[: len(html) // 2])


# --- Matching what students type ----------------------------------------------


@pytest.mark.parametrize(
    "specialization, language",
    [
        ("Informatica", "română"),
        ("Informatică", "romana"),
        ("  informatica ", "ROMÂNĂ"),
        ("Computer Science", "Romanian"),
    ],
)
def test_find_cohort_accepts_natural_input(links, specialization, language):
    assert find_cohort(links, specialization, language, 1).cohort_code == "I1"


def test_split_program_with_diacritics():
    assert split_program("Informatică - în limba engleză") == ("Informatică", "engleza")
    assert split_program("Ingineria Informației în limba maghiară") == ("Ingineria Informației", "maghiara")


@pytest.mark.parametrize("language", ["germana", "engleza", "German", "germana si engleza", "engleză și germană"])
def test_bilingual_programme_matches_either_language(links, language):
    name = "Sisteme informatice avansate: modelare, proiectare, dezvoltare"
    cohort = find_cohort(links, name, language, 1)
    assert cohort.cohort_code == "MaSIA1"
    assert cohort.teaching_language == "germana si engleza"


@pytest.mark.parametrize("language, code", [("engleza", "IE1"), ("germana", "IG1")])
def test_single_language_lines_stay_separate(links, language, code):
    assert find_cohort(links, "Informatica", language, 1).cohort_code == code


def test_exact_language_wins_over_bilingual(links):
    english = find_cohort(links, "Informatica", "engleza", 1)
    both = replace(english, teaching_language="germana si engleza", cohort_code="IGE1")
    assert find_cohort([both, english], "Informatica", "engleza", 1) == english
