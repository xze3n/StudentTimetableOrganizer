# Week 8 — SQLite cache, refresh and data validation

## What we built

| Module | Purpose |
|---|---|
| `ingest/store.py` | SQLite store: `snapshots` and `activities` tables, one active snapshot per (academic year, semester, cohort), old snapshots kept, `diff_activities` between snapshots. |
| `ingest/cache.py` | `get_timetable(...)`: returns the cached snapshot, or fetches it; `refresh=True` re-fetches and reports what changed. CLI: `python -m ingest.cache 2026-2027 1 Informatica romana 1 [--refresh]`. |
| `ingest/check.py` | Semester-wide checks: required-field coverage, duplicate publications, overlaps for the same students. CLI: `python -m ingest.check 2026-2027 1`. |

The database lives in `data/timetable.sqlite` (ignored by git).

### Refresh behaviour

| Situation | Result |
|---|---|
| Cached snapshot exists, no refresh | `cached`, no network access |
| No cached snapshot | fetch, validate, store → `fetched` |
| Refresh, same content | `unchanged`; only `checked_at` is updated, no new snapshot |
| Refresh, different content | new active snapshot, old one kept → `updated` with a diff (added / removed / changed) |
| Refresh fails (network, changed layout, invalid row) | `fallback` to the cached snapshot, with the error and the cached fetch time |
| No cache and the fetch fails | the error is raised |
| Unknown programme or year | `LookupError` (not treated as a fetch failure) |

A snapshot is written in one transaction, so a failed save never leaves partial data or removes the active snapshot. A *changed* activity in the diff is an old and a new record of the same course, activity type and formation (for example a lab moved to another room or time).

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

## Finding: optional courses overlap with required ones

The 302 overlaps are not data errors. They are mostly **optional courses** scheduled in parallel with required activities or with each other, for example:

- *Psihologie educationala* (teacher-training module) on Friday 12–14 for all of I1, at the same time as group 215/1's *Arhitectura sistemelor de calcul* lab;
- *Demonstrarea teoremelor in Lean* and *Aplicatii ale geometriei*, two M2 lectures on Wednesday 8–10 (students choose one).

The tabular pages do not mark which courses are optional. This affects the solver (Week 10): "every required activity stays covered" needs to know which activities are required. Options we will evaluate:

1. read the discipline pages (`disc/<code>.html`) or the faculty curriculum, if they mark optional courses;
2. ask the student which optional courses they take, and treat the rest of the parallel ones as not required.

## Tests

`tests/test_store.py` (15 tests) covers the store round trip, cache hit without network, unchanged refresh, refresh with a moved lab and its diff, fallback on network failure and on a changed page layout, the no-cache error, 4-digit groups (saved `IA2.html`), and the validation report. Total: 36 tests, run with `python -m pytest`.
