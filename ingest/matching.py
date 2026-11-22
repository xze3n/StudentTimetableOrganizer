"""Match what students type against the names on the official pages."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import TypeVar

T = TypeVar("T")  # anything with specialization, teaching_language and study_year

# English names, as used in the structured requests (Milestone 2, section 2.1).
LANGUAGE_ALIASES = {
    "romanian": "romana",
    "english": "engleza",
    "hungarian": "maghiara",
    "german": "germana",
}
SPECIALIZATION_ALIASES = {"computer science": "informatica"}


def normalize(text: str) -> str:
    """'  Informatică ' -> 'informatica': no case, diacritics or extra spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.casefold().split())


def specialization_key(text: str) -> str:
    name = normalize(text)
    return SPECIALIZATION_ALIASES.get(name, name)


def language_set(text: str) -> frozenset[str]:
    """'germana si engleza' -> {'germana', 'engleza'}."""
    names = re.split(r" (?:si|and) ", normalize(text))
    return frozenset(LANGUAGE_ALIASES.get(n, n) for n in names if n)


def context_key(specialization: str, teaching_language: str, study_year: int) -> tuple:
    return specialization_key(specialization), language_set(teaching_language), study_year


def best_match(
    candidates: Iterable[T], specialization: str, teaching_language: str, study_year: int
) -> T | None:
    """The candidate for a student context.

    A bilingual programme matches either of its languages, but a programme
    taught only in the requested language is preferred.
    """
    name, wanted, year = context_key(specialization, teaching_language, study_year)
    bilingual = None
    for candidate in candidates:
        c_name, taught, c_year = context_key(
            candidate.specialization, candidate.teaching_language, candidate.study_year
        )
        if (c_name, c_year) != (name, year):
            continue
        if taught == wanted:
            return candidate
        if bilingual is None and wanted and wanted < taught:
            bilingual = candidate
    return bilingual
