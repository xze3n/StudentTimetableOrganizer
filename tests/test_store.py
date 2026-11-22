"""Tests for the SQLite cache, refresh/diff, fallback and semester checks."""

from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
import requests

from ingest.cache import get_timetable
from ingest.check import validate_activities
from ingest.fetch import find_cohort
from ingest.parser import ParseError, parse_cohort_page, parse_index
from ingest.store import TimetableStore, diff_activities

FIXTURES = Path(__file__).parent / "fixtures" / "2026-1"
BASE = "https://www.cs.ubbcluj.ro/files/orar/2026-1/tabelar/"
YEAR = "2026-2027"


def read(name: str) -> str:
    return (FIXTURES / name).read_bytes().decode("iso-8859-2")


class FakeSite:
    """Serves saved pages instead of the network; pages can be edited or broken."""

    def __init__(self):
        self.pages = {BASE + n: read(n) for n in ("index.html", "I1.html", "IA2.html")}
        self.down = False
        self.calls = 0

    def __call__(self, url: str) -> str:
        self.calls += 1
        if self.down:
            raise requests.ConnectionError("site unreachable")
        return self.pages[url]


@pytest.fixture
def site():
    return FakeSite()


@pytest.fixture
def store():
    s = TimetableStore(":memory:")
    yield s
    s.close()


def load(store, site, **kw):
    return get_timetable(store, YEAR, 1, "Informatica", "romana", 1, page_getter=site, **kw)


# --- 4-digit groups -----------------------------------------------------------


def test_four_digit_groups():
    links = parse_index(read("index.html"))
    cohort = find_cohort(links, "Inteligenta Artificiala", "engleza", 2)
    acts = parse_cohort_page(read("IA2.html"), academic_year=YEAR, semester=1, cohort=cohort, source_url=BASE + "IA2.html")
    assert len(acts) == 44
    assert sorted({a.group for a in acts if a.group}) == ["1021", "1022"]
    assert {a.subgroup for a in acts if a.formation.startswith("1021/")} == {"1", "2"}
    assert all(a.group is None for a in acts if a.formation == "IA2")
    assert Counter(a.week_pattern for a in acts) == {"all": 24, "odd": 13, "even": 7}


# --- store ----------------------------------------------------------------------


def test_first_load_fetches_and_stores(store, site):
    result = load(store, site)
    assert result.status == "fetched"
    assert len(result.activities) == 63
    snap = result.snapshot
    assert snap.is_active and snap.record_count == 63
    assert snap.source_url == BASE + "I1.html"
    assert snap.snapshot_id.startswith("2026-1-I1-")


def test_round_trip_keeps_every_field(store, site):
    first = load(store, site)
    fresh = parse_cohort_page(
        read("I1.html"), academic_year=YEAR, semester=1,
        cohort=find_cohort(parse_index(read("index.html")), "Informatica", "romana", 1),
        source_url=BASE + "I1.html",
    )
    assert sorted(first.activities, key=lambda a: a.activity_id) == sorted(fresh, key=lambda a: a.activity_id)


def test_second_load_uses_cache_without_network(store, site):
    load(store, site)
    site.calls = 0
    result = load(store, site)
    assert result.status == "cached"
    assert site.calls == 0


def test_refresh_unchanged_keeps_snapshot(store, site):
    first = load(store, site)
    again = load(store, site, refresh=True)
    assert again.status == "unchanged"
    assert again.snapshot.snapshot_id == first.snapshot.snapshot_id
    assert len(store.list_snapshots(YEAR, 1, "I1")) == 1


def test_refresh_with_changes_creates_new_snapshot_and_diff(store, site):
    first = load(store, site)
    page = site.pages[BASE + "I1.html"]
    # Move the Monday 18-20 lab of 211/2 to room C310.
    page = page.replace('<a href="../sali/L002.html" >L002</a>', '<a href="../sali/C310.html" >C310</a>', 1)
    site.pages[BASE + "I1.html"] = page

    result = load(store, site, refresh=True)
    assert result.status == "updated"
    assert result.snapshot.snapshot_id != first.snapshot.snapshot_id
    assert result.diff.summary() == "0 added, 0 removed, 1 changed"
    [(old, new)] = result.diff.changed
    assert (old.room, new.room) == ("L002", "C310")
    assert old.course_name == new.course_name == "Arhitectura sistemelor de calcul"

    snaps = store.list_snapshots(YEAR, 1, "I1")
    assert len(snaps) == 2  # the old snapshot is kept
    assert [s.is_active for s in snaps] == [False, True]


def test_failed_refresh_falls_back_to_cache(store, site):
    first = load(store, site)
    site.down = True
    result = load(store, site, refresh=True)
    assert result.status == "fallback"
    assert "site unreachable" in result.error
    assert result.snapshot.snapshot_id == first.snapshot.snapshot_id
    assert "fetched " + first.snapshot.fetched_at in result.describe()


def test_broken_page_does_not_replace_cache(store, site):
    first = load(store, site)
    site.pages[BASE + "I1.html"] = site.pages[BASE + "I1.html"].replace("<th>Sala</th>", "<th>Locatie</th>")
    result = load(store, site, refresh=True)
    assert result.status == "fallback"
    assert "ParseError" in result.error
    assert store.active_snapshot(YEAR, 1, "I1").snapshot_id == first.snapshot.snapshot_id


def test_no_cache_and_site_down_raises(store, site):
    site.down = True
    with pytest.raises(requests.ConnectionError):
        load(store, site)


def test_unknown_programme_raises_lookup_error(store, site):
    with pytest.raises(LookupError):
        get_timetable(store, YEAR, 1, "Informatica", "romana", 5, page_getter=site)


def test_empty_snapshot_rejected(store):
    with pytest.raises(ValueError):
        store.save_snapshot([], source_url="x")


# --- diff -----------------------------------------------------------------------


def test_diff_added_removed_changed(store, site):
    acts = load(store, site).activities
    a, b, c = acts[0], acts[1], acts[2]
    moved = replace(c, day="Saturday" if c.day != "Saturday" else "Monday")
    extra = replace(a, course_name="Curs nou", formation="211")
    new = [x for x in acts if x not in (b, c)] + [moved, extra]
    d = diff_activities(acts, new)
    assert d.added == [extra]
    assert d.removed == [b]
    assert d.changed == [(c, moved)]


# --- semester checks ------------------------------------------------------------


def test_validation_report(store, site):
    acts = load(store, site).activities
    report = validate_activities(acts)
    assert report.total == 63
    assert all(report.coverage(f) == 1.0 for f in ("course_name", "room", "teacher"))
    assert report.duplicates == []


def test_validation_flags_duplicates_and_overlaps(store, site):
    acts = load(store, site).activities
    lab = next(a for a in acts if a.formation == "211/2" and a.day == "Monday" and a.start_time == "18:00")
    twin = replace(lab, room="C310")  # same lab published twice with another room
    clash = replace(lab, course_name="Alt curs", formation="211")  # whole group 211 at the same time
    report = validate_activities(acts + [twin, clash])
    assert (lab, twin) in report.duplicates or (twin, lab) in report.duplicates
    assert any({lab.course_name, "Alt curs"} == {x.course_name, y.course_name} for x, y in report.overlaps)


def test_odd_and_even_weeks_do_not_overlap(store, site):
    acts = load(store, site).activities
    lab = next(a for a in acts if a.formation == "211/2" and a.week_pattern == "all")
    odd = replace(lab, week_pattern="odd", frequency_label="sapt. 1")
    even = replace(lab, course_name="Alt curs", week_pattern="even", frequency_label="sapt. 2")
    report = validate_activities([odd, even])
    assert report.overlaps == []
