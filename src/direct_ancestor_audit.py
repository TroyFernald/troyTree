from __future__ import annotations

import sqlite3
from collections import deque
from collections.abc import Mapping

from .date_validation import find_date_issues
from .paths import WORKING_DB

DEFAULT_ROOT_PERSON_ID = "@I322454162854@"
PRIORITY_SURNAMES = {
    "Fernald",
    "Bagley",
    "Meservie",
    "Meserve",
    "Fuller",
    "McKay",
    "Pierce",
    "Fairfield",
    "Soper",
    "Adams",
    "Grant",
    "Cookson",
}
PRIORITY_PLACES = ("Maine", "New Hampshire", "Massachusetts", "Nova Scotia")


def ancestor_generations(con: sqlite3.Connection, root_person_id: str = DEFAULT_ROOT_PERSON_ID) -> dict[str, int]:
    parents_by_child: dict[str, set[str]] = {}
    for child_id, parent_id in con.execute(
        """
        SELECT related_person_id AS child_id, person_id AS parent_id
        FROM family_relationships
        WHERE relationship_type = 'parent'
        """
    ):
        parents_by_child.setdefault(child_id, set()).add(parent_id)

    generations = {root_person_id: 0}
    queue = deque([root_person_id])
    while queue:
        person_id = queue.popleft()
        next_generation = generations[person_id] + 1
        for parent_id in sorted(parents_by_child.get(person_id, set())):
            if parent_id not in generations or next_generation < generations[parent_id]:
                generations[parent_id] = next_generation
                queue.append(parent_id)
    return generations


def audit_flags(person: Mapping) -> list[str]:
    flags: list[str] = []
    if not person["source_count"]:
        flags.append("no sources")
    if person["confidence_status"] == "weak_source_only":
        flags.append("weak source only")
    if not person["birth_date"]:
        flags.append("missing birth date")
    if not person["birth_place"]:
        flags.append("missing birth place")
    if person["generation"] != 0 and not person["death_date"]:
        flags.append("missing death date")
    if person["generation"] != 0 and not person["death_place"]:
        flags.append("missing death place")
    for issue in find_date_issues(person["birth_date"], person["death_date"], person_name=person["full_name"]):
        flags.append(issue.message)
    surname = person["surname"] or ""
    place_text = f"{person['birth_place']} {person['death_place']}"
    if surname in PRIORITY_SURNAMES:
        flags.append("priority surname")
    if any(place in place_text for place in PRIORITY_PLACES):
        flags.append("priority place")
    return flags


def priority_for(person: Mapping, generation: int, flags: list[str]) -> int:
    if generation == 0:
        return 999
    priority = generation * 10
    material = any(
        flag in {"no sources", "weak source only", "missing birth date", "missing birth place"}
        or ("date" in flag.lower() and "missing death" not in flag.lower())
        for flag in flags
    )
    if "no sources" in flags:
        priority -= 30
    if "weak source only" in flags:
        priority -= 20
    if any("Death date is before birth date" in flag or "115" in flag for flag in flags):
        priority -= 25
    if material and "priority surname" in flags:
        priority -= 5
    if material and "priority place" in flags:
        priority -= 5
    if material and 4 <= generation <= 8:
        priority -= 10
    return max(1, priority)


def should_queue(generation: int, flags: list[str]) -> bool:
    if generation == 0 or generation > 12:
        return False
    material_flags = {
        "no sources",
        "weak source only",
        "missing birth date",
        "missing birth place",
    }
    has_material_flag = any(flag in material_flags for flag in flags)
    has_date_problem = any("date" in flag.lower() and "missing death" not in flag.lower() for flag in flags)
    return has_material_flag or has_date_problem


def update_direct_ancestor_audit(
    db_path=WORKING_DB,
    root_person_id: str = DEFAULT_ROOT_PERSON_ID,
    rebuild_queue: bool = True,
) -> int:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        generations = ancestor_generations(con, root_person_id)
        con.execute("DELETE FROM direct_ancestor_audit")
        if rebuild_queue:
            con.execute("DELETE FROM research_queue WHERE notes = 'generated from direct ancestor audit'")

        for person_id, generation in generations.items():
            person = con.execute("SELECT * FROM people WHERE person_id = ?", (person_id,)).fetchone()
            if not person:
                continue
            relationship = "root" if generation == 0 else "direct ancestor"
            con.execute(
                """
                UPDATE people
                SET generation = ?, relationship_to_root = ?
                WHERE person_id = ?
                """,
                (generation, relationship, person_id),
            )
            person_for_flags = {**dict(person), "generation": generation}
            flags = audit_flags(person_for_flags)
            priority = priority_for(person_for_flags, generation, flags)
            con.execute(
                """
                INSERT INTO direct_ancestor_audit (
                    person_id, person_name, generation, birth_date, birth_place,
                    death_date, death_place, spouse_names, parent_names,
                    source_count, confidence_status, audit_flags, priority, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    person_id,
                    person["full_name"],
                    generation,
                    person["birth_date"],
                    person["birth_place"],
                    person["death_date"],
                    person["death_place"],
                    person["spouse_names"],
                    person["parent_names"],
                    person["source_count"],
                    person["confidence_status"],
                    "; ".join(flags),
                    priority,
                    "",
                ),
            )
            if rebuild_queue and should_queue(generation, flags):
                con.execute(
                    """
                    INSERT INTO research_queue (
                        person_id, person_name, priority, reason, search_terms,
                        target_sources, status, assigned_to, created_date,
                        last_researched_date, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, 'open', '', date('now'), '', ?)
                    """,
                    (
                        person_id,
                        person["full_name"],
                        priority,
                        "; ".join(flags),
                        f'"{person["full_name"]}" genealogy',
                        "FamilySearch, WikiTree, Find a Grave, Internet Archive, Google Books, town histories, census indexes",
                        "generated from direct ancestor audit",
                    ),
                )
        con.commit()
        return len(generations)
    finally:
        con.close()


if __name__ == "__main__":
    count = update_direct_ancestor_audit()
    print(f"Tagged {count} direct ancestors/root people")
