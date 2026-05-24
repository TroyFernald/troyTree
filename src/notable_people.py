from __future__ import annotations

import re
import sqlite3

from .paths import WORKING_DB

MAYFLOWER_NAMES = {
    "john alden": "Mayflower passenger",
    "priscilla mullins": "Mayflower passenger",
    "john howland": "Mayflower passenger",
    "elizabeth tilley": "Mayflower passenger",
    "stephen hopkins": "Mayflower passenger",
    "william brewster": "Mayflower elder/passenger",
    "john tilley": "Mayflower passenger",
    "joan hurst": "Mayflower family connection",
    "isaac allerton": "Mayflower passenger",
    "william bradford": "Mayflower passenger/governor",
    "edward winslow": "Mayflower passenger/governor",
    "myles standish": "Mayflower military leader",
    "richard warren": "Mayflower passenger",
    "george soule": "Mayflower passenger",
    "francis cooke": "Mayflower passenger",
}

COLONIAL_PUBLIC_FIGURES = {
    "maj. general nathaniel folsom": "Revolutionary-era New Hampshire military/political figure",
    "nathaniel folsom": "Revolutionary-era New Hampshire military/political figure",
}

ROYAL_NOBLE_TERMS = {
    "king of": "Royal title claim",
    "queen of": "Royal title claim",
    "prince of": "Royal/noble title claim",
    "princess": "Royal/noble title claim",
    "duke of": "Noble title claim",
    "duchess": "Noble title claim",
    "earl of": "Noble title claim",
    "countess": "Noble title claim",
    "lord of": "Noble title claim",
    "lady ": "Noble title claim",
    "sir ": "Noble/knightly title claim",
    "charlemagne": "Medieval royal descent claim",
    "tudor": "Tudor/royal descent claim",
    "capet": "French royal descent claim",
    "plantagenet": "Plantagenet royal descent claim",
}

MILITARY_PUBLIC_TERMS = {
    "maj. general": "Military title",
    "major general": "Military title",
    "capt": "Military title",
    "captain": "Military title",
    "lieut": "Military title",
    "ensign": "Military title",
    "private": "Military title",
    "revolutionary war": "Revolutionary War reference",
}


def _normalized_name(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower()).strip()


def _risk_for(category: str, generation: int | None) -> str:
    if category in {"royal_noble", "medieval_descent"}:
        return "high"
    if generation is not None and generation >= 12:
        return "medium-high"
    if category == "mayflower":
        return "medium"
    return "medium"


def _candidate_rows(person: sqlite3.Row) -> list[dict]:
    name = person["full_name"] or ""
    normalized = _normalized_name(name)
    text = " ".join(
        str(person[key] or "")
        for key in ["full_name", "birth_place", "death_place", "notes"]
        if key in person.keys()
    ).lower()
    generation = person["generation"]
    rows: list[dict] = []

    for notable_name, reason in MAYFLOWER_NAMES.items():
        if notable_name in normalized or "mayflower" in text and notable_name.split()[0] in normalized:
            rows.append({"category": "mayflower", "notable_reason": reason})

    for notable_name, reason in COLONIAL_PUBLIC_FIGURES.items():
        if notable_name in normalized:
            rows.append({"category": "colonial_public_figure", "notable_reason": reason})

    for term, reason in ROYAL_NOBLE_TERMS.items():
        if term in text:
            category = "medieval_descent" if term in {"charlemagne", "capet", "plantagenet", "tudor"} else "royal_noble"
            rows.append({"category": category, "notable_reason": reason})

    for term, reason in MILITARY_PUBLIC_TERMS.items():
        if re.search(rf"\b{re.escape(term)}\b", text):
            rows.append({"category": "military_title", "notable_reason": reason})

    deduped = []
    seen = set()
    for row in rows:
        key = (row["category"], row["notable_reason"])
        if key not in seen:
            seen.add(key)
            row["risk_level"] = _risk_for(row["category"], generation)
            deduped.append(row)
    return deduped


def rebuild_notable_people(db_path=WORKING_DB) -> int:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        con.execute("DELETE FROM notable_person_candidate")
        people = con.execute(
            """
            SELECT *
            FROM people
            WHERE relationship_to_root IN ('root', 'direct ancestor')
            """
        ).fetchall()
        for person in people:
            for candidate in _candidate_rows(person):
                con.execute(
                    """
                    INSERT OR IGNORE INTO notable_person_candidate (
                        person_id, person_name, generation, relationship_to_root,
                        birth_date, death_date, birth_place, death_place, category,
                        notable_reason, risk_level, proof_status, review_notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unverified', ?)
                    """,
                    (
                        person["person_id"],
                        person["full_name"],
                        person["generation"],
                        person["relationship_to_root"],
                        person["birth_date"],
                        person["death_date"],
                        person["birth_place"],
                        person["death_place"],
                        candidate["category"],
                        candidate["notable_reason"],
                        candidate["risk_level"],
                        "Treat as GEDCOM claim until supported by citations and proof path.",
                    ),
                )
        con.commit()
        return con.execute("SELECT COUNT(*) FROM notable_person_candidate").fetchone()[0]
    finally:
        con.close()


if __name__ == "__main__":
    print(f"Notable candidates: {rebuild_notable_people()}")
