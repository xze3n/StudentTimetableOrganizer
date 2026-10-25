# RFC: Timetable Optimization Agent

## 1. Problem Definition

Every semester, students have to build a personal timetable from university schedules that list dozens of courses, lab groups and seminar groups. Today this is done by hand: students cross-check spreadsheets, look for overlaps and trade groups with colleagues by trial and error. The result is often a fragmented week, with long gaps between classes, early-morning sessions and more days on campus than needed. This hits hardest for students who commute or work part-time.

The problem has three parts:

- **Too many combinations.** Picking one group per course gives a number of possible timetables that grows quickly, so no one can check them all by hand.
- **Preferences are personal and informal.** Students think in terms like "no early mornings" or "I work on Fridays", not in course codes and time slots.
- **The information is scattered and hard to trust.** Course lists, schedules and prerequisite rules sit in separate documents, and a mistake (a missed mandatory course, a hidden overlap) is only found once the semester has started.

**Goal:** let a student describe what they want in plain language and get back a valid, conflict-free timetable that covers all required courses and fits their preferences as closely as possible.

## 2. State of the Art

| Approach | Pros | Cons |
|---|---|---|
| **Manual planning** (official spreadsheets, university portals) | Always uses the official data; no extra tools needed | Slow and error-prone; no optimization; overlaps are easy to miss |
| **Schedule builders** (e.g. Coursicle, Semester.ly, generic "schedule maker" sites) | Show conflicts visually; some generate every valid combination | Need structured input (codes, filters); preferences can't be stated naturally; usually tied to specific universities; little support for local rules such as prerequisites |
| **Institutional timetabling systems** (e.g. UniTime) | Strong optimization over the whole university | Built for administrators to schedule rooms and staff, not for one student's personal preferences; not open to students |
| **General-purpose AI chatbots** | Understand natural language; easy to use | No access to the real university data; can't reliably solve scheduling problems; may invent courses or time slots that don't exist |

In short, the existing tools either **understand the student** (chatbots) or **compute correct timetables** (schedule builders, institutional systems). None does both well for an individual student working from their own university's data.

## 3. Proposal

We propose a **conversational timetable assistant** that brings these strengths together. The student describes their situation in everyday language, and the assistant:

1. **Understands the request.** A language model specialized for this task turns informal requests into precise scheduling preferences.
2. **Grounds itself in the official data.** It answers questions and builds timetables only from the university's real course catalog, schedules and prerequisite rules. It never relies on its own memory.
3. **Delegates the optimization.** It hands the actual scheduling to a dedicated solver, so results are mathematically correct rather than guessed.
4. **Delivers a usable result.** The final timetable can be exported directly into the student's personal calendar.

**What makes it different and better:**

- **Natural-language interaction combined with guaranteed correctness**, which chatbots can't offer and schedule builders don't attempt.
- **Personal preferences come first** (fewer campus days, no early classes, free workdays), unlike institutional systems that optimize for the university.
- **Trustworthy by design.** Every proposed timetable is checked automatically for zero overlaps and full coverage of mandatory courses. Requests for courses that don't exist in the official data are rejected rather than answered with a made-up schedule.
- **Adaptable.** Because the assistant works from the university's own documents, the same approach can be used for any faculty or university.

**Expected outcome:** less time spent planning, fewer scheduling mistakes and more compact weeks for students, with every suggestion traceable to official university data.
