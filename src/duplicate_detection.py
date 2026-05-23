from __future__ import annotations

from dataclasses import dataclass
import re

from rapidfuzz import fuzz


@dataclass(frozen=True)
class DuplicateCandidate:
    left_person_id: str
    right_person_id: str
    left_name: str
    right_name: str
    left_birth_date: str
    right_birth_date: str
    left_birth_place: str
    right_birth_place: str
    left_death_date: str
    right_death_date: str
    left_death_place: str
    right_death_place: str
    left_relationship_to_root: str
    right_relationship_to_root: str
    score: int
    reason: str


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _same(left: dict, right: dict, field: str) -> bool:
    return bool(_norm(left.get(field))) and _norm(left.get(field)) == _norm(right.get(field))


def _year(value: str | None) -> int | None:
    match = re.search(r"(1[0-9]{3}|20[0-9]{2})", value or "")
    return int(match.group(1)) if match else None


def _conflicting_years(left: dict, right: dict, field: str, tolerance: int = 2) -> bool:
    left_year = _year(left.get(field))
    right_year = _year(right.get(field))
    return left_year is not None and right_year is not None and abs(left_year - right_year) > tolerance


def _compatible_years(left: dict, right: dict, field: str, tolerance: int = 2) -> bool:
    left_year = _year(left.get(field))
    right_year = _year(right.get(field))
    return left_year is not None and right_year is not None and abs(left_year - right_year) <= tolerance


def _generation_gap(left: dict, right: dict) -> int | None:
    try:
        left_generation = int(left.get("generation"))
        right_generation = int(right.get("generation"))
    except (TypeError, ValueError):
        return None
    return abs(left_generation - right_generation)


def _near_place(left: dict, right: dict, field: str) -> bool:
    left_place = _norm(left.get(field))
    right_place = _norm(right.get(field))
    if not left_place or not right_place:
        return False
    left_parts = {part.strip() for part in left_place.split(",") if part.strip()}
    right_parts = {part.strip() for part in right_place.split(",") if part.strip()}
    return bool(left_parts & right_parts)


def find_duplicate_candidates(people: list[dict], threshold: int = 88) -> list[DuplicateCandidate]:
    candidates: list[DuplicateCandidate] = []
    for index, left in enumerate(people):
        for right in people[index + 1 :]:
            name_score = fuzz.token_sort_ratio(left.get("full_name", ""), right.get("full_name", ""))
            same_birth = _same(left, right, "birth_date")
            same_death = _same(left, right, "death_date")
            same_birth_place = _same(left, right, "birth_place")
            same_death_place = _same(left, right, "death_place")
            near_birth_place = _near_place(left, right, "birth_place")
            near_death_place = _near_place(left, right, "death_place")
            same_parent_names = _same(left, right, "parent_names")
            same_spouse_names = _same(left, right, "spouse_names")
            conflicting_birth_year = _conflicting_years(left, right, "birth_date")
            conflicting_death_year = _conflicting_years(left, right, "death_date")
            compatible_birth_year = _compatible_years(left, right, "birth_date")
            compatible_death_year = _compatible_years(left, right, "death_date")
            generation_gap = _generation_gap(left, right)
            one_direct = "direct ancestor" in {
                left.get("relationship_to_root", ""),
                right.get("relationship_to_root", ""),
            }

            score = int(name_score)
            reasons = [f"name similarity {int(name_score)}"]
            if same_birth:
                score += 12
                reasons.append("same birth date")
            if same_death:
                score += 12
                reasons.append("same death date")
            if same_birth_place:
                score += 8
                reasons.append("same birth place")
            elif near_birth_place:
                score += 4
                reasons.append("near birth place")
            if same_death_place:
                score += 8
                reasons.append("same death place")
            elif near_death_place:
                score += 4
                reasons.append("near death place")
            if same_parent_names:
                score += 12
                reasons.append("same parents")
            if same_spouse_names:
                score += 10
                reasons.append("same spouse")
            if one_direct:
                reasons.append("direct ancestor involved")
            if conflicting_birth_year:
                score -= 35
                reasons.append("conflicting birth years")
            if conflicting_death_year:
                score -= 35
                reasons.append("conflicting death years")
            if generation_gap is not None and generation_gap > 1:
                score -= 30
                reasons.append(f"generation gap {generation_gap}")

            has_identity_clue = (
                same_birth
                or same_death
                or compatible_birth_year
                or compatible_death_year
                or same_parent_names
                or same_spouse_names
            )
            has_context_clue = (
                same_parent_names
                or same_spouse_names
                or same_birth_place
                or same_death_place
                or near_birth_place
                or near_death_place
            )
            generationally_plausible = generation_gap is None or generation_gap <= 1
            same_name_with_only_place = (
                name_score == 100
                and has_context_clue
                and not conflicting_birth_year
                and not conflicting_death_year
                and generationally_plausible
            )
            if score >= threshold and generationally_plausible and (has_identity_clue or same_name_with_only_place):
                candidates.append(
                    DuplicateCandidate(
                        left.get("person_id", ""),
                        right.get("person_id", ""),
                        left.get("full_name", ""),
                        right.get("full_name", ""),
                        left.get("birth_date", ""),
                        right.get("birth_date", ""),
                        left.get("birth_place", ""),
                        right.get("birth_place", ""),
                        left.get("death_date", ""),
                        right.get("death_date", ""),
                        left.get("death_place", ""),
                        right.get("death_place", ""),
                        left.get("relationship_to_root", ""),
                        right.get("relationship_to_root", ""),
                        min(score, 100),
                        "; ".join(reasons),
                    )
                )
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
