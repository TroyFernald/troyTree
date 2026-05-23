from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re

from dateutil import parser


@dataclass(frozen=True)
class DateIssue:
    field: str
    message: str


def parse_genealogy_date(value: str | None) -> date | None:
    if not value:
        return None
    text = normalize_genealogy_date_text(value)
    if not text:
        return None
    if not re.search(r"\b\d{3,4}\b", text):
        return None
    try:
        default = datetime(1, 1, 1)
        parsed = parser.parse(text, fuzzy=True, default=default)
        if parsed.year == 1:
            return None
        return parsed.date()
    except (ValueError, OverflowError):
        return None


def normalize_genealogy_date_text(value: str | None) -> str:
    text = (value or "").strip()
    text = text.replace("?", "")
    text = re.sub(r",(?=\d)", ", ", text)
    text = re.sub(r"\b(c|ca|circa|abt|about|aft|after|bef|before|est|estimated|cal|calculated)\b\.?", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def years_between(start: date, end: date) -> int:
    return end.year - start.year - ((end.month, end.day) < (start.month, start.day))


def find_date_issues(
    birth_date: str | None,
    death_date: str | None,
    *,
    person_name: str = "",
) -> list[DateIssue]:
    issues: list[DateIssue] = []
    birth = parse_genealogy_date(birth_date)
    death = parse_genealogy_date(death_date)

    if birth_date and not birth:
        issues.append(DateIssue("birth_date", f"Could not parse birth date for {person_name}".strip()))
    if death_date and not death:
        issues.append(DateIssue("death_date", f"Could not parse death date for {person_name}".strip()))
    if birth and death:
        if death < birth:
            issues.append(DateIssue("death_date", "Death date is before birth date"))
        elif years_between(birth, death) > 115:
            issues.append(DateIssue("death_date", "Lifespan exceeds 115 years"))
    return issues
