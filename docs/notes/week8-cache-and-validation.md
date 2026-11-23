# Week 8 — SQLite cache, refresh and data validation

## What we built

| Module | Purpose |
|---|---|
| `ingest/store.py` | SQLite store: `snapshots` and `activities` tables, one active snapshot per student context (academic year, semester, specialization, language, study year), old snapshots kept, `diff_activities` between snapshots. |
| `ingest/cache.py` | `get_timetable(...)`: returns the cached snapshot, or fetches it; `refresh=True` re-fetches and reports what changed. CLI: `python -m ingest.cache 2026-2027 1 Informatica romana 1 [--refresh]`. |
| `ingest/matching.py` | Matches student input to official names: ignores case, diacritics and extra spaces, accepts English language names and *Computer Science*, and matches a bilingual programme under either language. |
| `ingest/check.py` | Semester-wide checks: required-field coverage, duplicate publications, overlaps for the same students. CLI: `python -m ingest.check 2026-2027 1`. |

The database lives in `data/timetable.sqlite` (ignored by git).

### Refresh behaviour

| Situation | Result |
|---|---|
| Cached snapshot exists, no refresh | `cached`, no network access |
| No cached snapshot, classes published | fetch, validate, store → `fetched` |
| Refresh, same content | new active snapshot with a new `snapshot_id`, old one kept → `unchanged` |
| Refresh, different content | new active snapshot, old one kept → `updated` with a diff (added / removed / changed) |
| Refresh fails (network, changed layout, incomplete page, invalid row, cohort missing from the index) | `fallback` to the cached snapshot, with the error and the cached fetch time |
| No cache and the fetch fails | the error is raised |
| No cache and unknown programme or year | `LookupError` |
| No cache and no classes published | `empty`; nothing is stored, so the next request checks the site again |
| Refresh finds no classes | `fallback` to the cached snapshot, with a warning |

A refresh that finds the same cohort under a new page code replaces the old active snapshot.

A snapshot is written in one transaction, so a failed save never leaves partial data or removes the active snapshot. A *changed* activity in the diff is an old and a new record of the same course, activity type and formation (for example a lab moved to another room or time). When several records qualify, the most similar are paired first.

## Checks on 2026–2027 semester I

**All 75 cohort pages, 1 803 activities.**

| Check | Result |
|---|---|
| Pages parsed | 75 / 75 |
| Required-field coverage (course, type, formation, day, start, end, room, teacher) | 100% for every field |
| Week patterns | 1 133 every week, 351 odd, 319 even |
| Duplicate publications (same course, type, audience and slot) | 0 |
| Comparison with the source: every published row (2 540 rows in 131 group tables) re-read with an independent regex and matched against the stored records | 2 540 / 2 540 matched |
| Overlaps for the same students | 302 (see below) |

The comparison with the source covers every group and subgroup, not just a sample; the 2 540 published rows collapse to 1 803 activities because lectures and other whole-cohort activities are repeated in each group's table.

## Parser rules

- A page must end with `</html>` and have one table per `Grupa` heading, otherwise it is rejected as incomplete.
- A formation must be the page's cohort code or a group/subgroup number.
- Every link in the index must be readable; none is skipped silently.
- The site publishes empty timetables in two ways, both valid: group tables without rows (`StEduID1` in 2026-1) and a title without any groups (`PDAE1` in 2025-1).
- The bilingual master's is stored with `teaching_language` = `germana si engleza`. Code that filters by language must use `ingest.matching`, not string equality.

## Finding: optional courses overlap with required ones

The 302 overlaps are not data errors. They are mostly **optional courses** scheduled in parallel with required activities or with each other, for example:

- *Psihologie educationala* (teacher-training module) on Friday 12–14 for all of I1, at the same time as group 215/1's *Arhitectura sistemelor de calcul* lab;
- *Demonstrarea teoremelor in Lean* and *Aplicatii ale geometriei*, two M2 lectures on Wednesday 8–10 (students choose one).

The tabular pages do not mark which courses are optional. This affects the solver (Week 10): "every required activity stays covered" needs to know which activities are required. Options we will evaluate:

1. read the discipline pages (`disc/<code>.html`) or the faculty curriculum, if they mark optional courses;
2. ask the student which optional courses they take, and treat the rest of the parallel ones as not required.

## Tests

`tests/test_store.py` covers the store round trip, cache hit without network, a new snapshot on every refresh, diffs, fallback, empty timetables, renamed page codes, metadata changes, 4-digit groups (saved `IA2.html`) and the validation report. `tests/test_ingest.py` covers URLs, parsing, incomplete and empty pages, and input matching. Total: 80 tests, run with `python -m pytest`.
