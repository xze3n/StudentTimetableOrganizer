# Week 7 — Inspection of the official timetable pages

Semester inspected: **2026–2027, semester I** (`https://www.cs.ubbcluj.ro/files/orar/2026-1/`).

## Page structure

- `tabelar/index.html` lists every programme (row) and study year (column) with a link to one **cohort page**, e.g. `I1.html` = *Informatica – linia de studiu romana*, year 1. The index has **75 cohort pages** (bachelor and master).
- Cohort codes are not only `<letters><digit>`: master programmes use codes such as `MaMetModDid1` and `MaAI4CI1`, so the URL builder accepts any alphanumeric code (but no `/`, `.` or other characters).
- A cohort page has one `<h1>Grupa NNN</h1>` heading and one table per group. Every table has the same 8 columns: *Ziua, Orele, Frecventa, Sala, Formatia, Tipul, Disciplina, Cadrul didactic*.
- Pages are encoded in **ISO-8859-2**.

## Column values

| Column | Values seen | How we store it |
|---|---|---|
| Ziua | Luni … Vineri | English day name |
| Orele | whole hours, e.g. `8-10`, `8-9`, `15-17` | `start_time` / `end_time` as `HH:MM` |
| Frecventa | empty, `sapt. 1`, `sapt. 2` | label kept as published + `week_pattern` (`all` / `odd` / `even`) |
| Formatia | cohort code (`I1`), group (`211`, `1021`), subgroup (`211/2`, `1021/1`) | `formation` as published + derived `group` / `subgroup` |
| Tipul | Curs, Seminar, Laborator | as published |

`sapt. 1` is the first (odd) week and `sapt. 2` the second (even) week.

## Findings

- **Lectures are repeated** in every group's table. On `I1.html` there are 108 rows but only **63 distinct activities**; we de-duplicate them by a stable `activity_id` built from the identifying fields.
- Whole-cohort activities are not only lectures: some seminars and labs are also held for the whole cohort (formation = cohort code).
- Some programmes use **4-digit group numbers** (`1021`, `1311`); the first parser version only accepted 3 digits and wrongly treated these as whole-cohort activities. Fixed and covered by the all-pages check.
- The page header and every row are validated; an unknown frequency label, activity type, day, or a changed column layout raises `ParseError` instead of producing partial data.

## Check against all pages

Running the parser on all 75 cohort pages of 2026–2027 semester I: **75/75 parsed, 1 803 activities**, and every formation is either the page's own cohort code or a group/subgroup number.

Manual comparison on `I1.html` (group 211): Monday 18–20 lab *Arhitectura sistemelor de calcul* in L002 for 211/2, and the odd-week Wednesday 8–10 seminar with Drd. BOTA Daniel, both match the official page. These are now asserted in `tests/test_ingest.py`.

## Open points for Week 8

- Store records in SQLite with `snapshot_id` and `fetched_at`; implement refresh and the snapshot diff.
- Decide whether to keep the main index (`2026-1/`) notes (physical education, optional courses) as extra context; they are free text, not table rows.
- Add saved fixtures from a 4-digit-group programme (e.g. `IA2`) to the tests.
