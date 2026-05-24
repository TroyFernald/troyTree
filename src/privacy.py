"""Decide who counts as a living person and should be redacted before publishing.

A family site goes on the public internet even behind a password, so living
people are hidden by default: their name becomes "Living" and personal facts
(dates, places, relatives, media) are dropped. The published site can be rebuilt
with ``redact_living=False`` to show everyone.

A person is treated as living when there is no recorded death and either the
birth year is within the privacy window (100 years), or the birth is unknown but
they sit in the most recent generations (the root and their parents).
"""

from __future__ import annotations

from .date_validation import parse_genealogy_date

CURRENT_YEAR = 2026
PRIVACY_WINDOW = 100
LIVING_NAME = "Living"


def is_living(birth_date: str | None, death_date: str | None, generation=None) -> bool:
    if (death_date or "").strip():
        return False
    born = parse_genealogy_date(birth_date)
    if born is None:
        try:
            return generation is not None and int(generation) <= 1
        except (TypeError, ValueError):
            return False
    return born.year >= CURRENT_YEAR - PRIVACY_WINDOW
