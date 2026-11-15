"""Activity record schema for the official UBB timetable.

One ``Activity`` is one complete scheduled meeting, exactly as published on a
cohort page (``tabelar/<code>.html``), plus fields we derive from it.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

# Romanian day names used on the official pages -> English names we store.
DAYS = {
    "Luni": "Monday",
    "Marti": "Tuesday",
    "Miercuri": "Wednesday",
    "Joi": "Thursday",
    "Vineri": "Friday",
    "Sambata": "Saturday",
    "Duminica": "Sunday",
}

# Published frequency label -> week pattern used by the solver.
# "sapt. 1" is the first (odd) week, "sapt. 2" the second (even) week;
# an empty label means the activity takes place every week.
WEEK_PATTERNS = {
    "": "all",
    "sapt. 1": "odd",
    "sapt. 2": "even",
}

ACTIVITY_TYPES = {"Curs", "Seminar", "Laborator"}


@dataclass(frozen=True)
class Activity:
    academic_year: str  # e.g. "2026-2027"
    semester: int  # 1 or 2
    cohort_code: str  # page code, e.g. "I1"
    specialization: str  # e.g. "Informatica"
    teaching_language: str  # e.g. "romana"
    study_year: int
    course_name: str
    activity_type: str  # Curs / Seminar / Laborator
    formation: str  # as published: "I1", "211" or "211/2"
    group: str | None  # None for whole-cohort activities (lectures)
    subgroup: str | None  # "1" / "2" for half-group labs
    day: str  # English day name
    start_time: str  # "HH:MM"
    end_time: str  # "HH:MM"
    room: str
    teacher: str
    frequency_label: str  # exactly as published, "" when weekly
    week_pattern: str  # all / odd / even
    source_url: str

    @property
    def activity_id(self) -> str:
        """Stable ID from the fields that identify the meeting.

        Lectures are repeated in every group's table on the official page;
        they get the same ID, which is how we de-duplicate them.
        """
        key = "|".join(
            str(v)
            for v in (
                self.academic_year,
                self.semester,
                self.cohort_code,
                self.day,
                self.start_time,
                self.end_time,
                self.room,
                self.formation,
                self.activity_type,
                self.course_name,
                self.teacher,
                self.frequency_label,
            )
        )
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {"activity_id": self.activity_id, **asdict(self)}
