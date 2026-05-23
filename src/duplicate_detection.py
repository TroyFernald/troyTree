from __future__ import annotations

from dataclasses import dataclass
from rapidfuzz import fuzz


@dataclass(frozen=True)
class DuplicateCandidate:
    left_person_id: str
    right_person_id: str
    left_name: str
    right_name: str
    score: int
    reason: str


def find_duplicate_candidates(people: list[dict], threshold: int = 88) -> list[DuplicateCandidate]:
    candidates: list[DuplicateCandidate] = []
    for index, left in enumerate(people):
        for right in people[index + 1 :]:
            name_score = fuzz.token_sort_ratio(left.get("full_name", ""), right.get("full_name", ""))
            same_birth = bool(left.get("birth_date")) and left.get("birth_date") == right.get("birth_date")
            same_place = bool(left.get("birth_place")) and left.get("birth_place") == right.get("birth_place")
            score = int(name_score + (5 if same_birth else 0) + (3 if same_place else 0))
            if score >= threshold:
                candidates.append(
                    DuplicateCandidate(
                        left.get("person_id", ""),
                        right.get("person_id", ""),
                        left.get("full_name", ""),
                        right.get("full_name", ""),
                        min(score, 100),
                        "Similar name with matching date/place clues",
                    )
                )
    return candidates

