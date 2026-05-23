from __future__ import annotations

import sqlite3
from collections import defaultdict

from .date_validation import parse_genealogy_date, years_between
from .paths import WORKING_DB


def _add_issue(
    con: sqlite3.Connection,
    *,
    issue_type: str,
    severity: str,
    person_id: str,
    person_name: str,
    description: str,
    related_person_id: str = "",
    related_person_name: str = "",
    relationship_id: int | None = None,
    generation: int | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO validation_issue (
            issue_type, severity, person_id, person_name, related_person_id,
            related_person_name, relationship_id, generation, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            issue_type,
            severity,
            person_id,
            person_name,
            related_person_id,
            related_person_name,
            relationship_id,
            generation,
            description,
        ),
    )


def _ancestor_cycle_nodes(parent_edges: dict[str, set[str]]) -> set[str]:
    cycle_nodes: set[str] = set()
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(person_id: str, path: list[str]) -> None:
        if person_id in visiting:
            cycle_nodes.update(path[path.index(person_id) :] if person_id in path else [person_id])
            return
        if person_id in visited:
            return
        visiting.add(person_id)
        path.append(person_id)
        for parent_id in parent_edges.get(person_id, set()):
            visit(parent_id, path)
        path.pop()
        visiting.remove(person_id)
        visited.add(person_id)

    for child_id in parent_edges:
        visit(child_id, [])
    return cycle_nodes


def rebuild_validation_issues(db_path=WORKING_DB) -> int:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        con.execute("DELETE FROM validation_issue")

        people = {row["person_id"]: row for row in con.execute("SELECT * FROM people")}
        for person in people.values():
            birth = parse_genealogy_date(person["birth_date"])
            death = parse_genealogy_date(person["death_date"])
            if person["birth_date"] and not birth:
                _add_issue(
                    con,
                    issue_type="date_parse",
                    severity="medium",
                    person_id=person["person_id"],
                    person_name=person["full_name"],
                    generation=person["generation"],
                    description=f"Could not parse birth date: {person['birth_date']}",
                )
            if person["death_date"] and not death:
                _add_issue(
                    con,
                    issue_type="date_parse",
                    severity="medium",
                    person_id=person["person_id"],
                    person_name=person["full_name"],
                    generation=person["generation"],
                    description=f"Could not parse death date: {person['death_date']}",
                )
            if birth and death and death < birth:
                _add_issue(
                    con,
                    issue_type="death_before_birth",
                    severity="high",
                    person_id=person["person_id"],
                    person_name=person["full_name"],
                    generation=person["generation"],
                    description=f"Death date {person['death_date']} is before birth date {person['birth_date']}",
                )

        parent_edges: dict[str, set[str]] = defaultdict(set)
        parent_rels = con.execute(
            """
            SELECT fr.*, p.full_name parent_name, p.birth_date parent_birth, p.death_date parent_death,
                   p.generation parent_generation,
                   c.full_name child_name, c.birth_date child_birth, c.death_date child_death,
                   c.generation child_generation
            FROM family_relationships fr
            JOIN people p ON p.person_id = fr.person_id
            JOIN people c ON c.person_id = fr.related_person_id
            WHERE fr.relationship_type = 'parent'
            """
        ).fetchall()
        for rel in parent_rels:
            parent_edges[rel["related_person_id"]].add(rel["person_id"])
            if rel["person_id"] == rel["related_person_id"]:
                _add_issue(
                    con,
                    issue_type="self_parent",
                    severity="critical",
                    person_id=rel["person_id"],
                    person_name=rel["parent_name"],
                    related_person_id=rel["related_person_id"],
                    related_person_name=rel["child_name"],
                    relationship_id=rel["relationship_id"],
                    generation=rel["child_generation"],
                    description="Person is listed as their own parent",
                )
                continue

            parent_birth = parse_genealogy_date(rel["parent_birth"])
            parent_death = parse_genealogy_date(rel["parent_death"])
            child_birth = parse_genealogy_date(rel["child_birth"])
            if parent_birth and child_birth:
                parent_age = years_between(parent_birth, child_birth)
                if parent_age < 12:
                    _add_issue(
                        con,
                        issue_type="parent_too_young",
                        severity="high",
                        person_id=rel["person_id"],
                        person_name=rel["parent_name"],
                        related_person_id=rel["related_person_id"],
                        related_person_name=rel["child_name"],
                        relationship_id=rel["relationship_id"],
                        generation=rel["child_generation"],
                        description=f"Parent appears age {parent_age} at child birth",
                    )
                elif parent_age > 70:
                    _add_issue(
                        con,
                        issue_type="parent_too_old",
                        severity="medium",
                        person_id=rel["person_id"],
                        person_name=rel["parent_name"],
                        related_person_id=rel["related_person_id"],
                        related_person_name=rel["child_name"],
                        relationship_id=rel["relationship_id"],
                        generation=rel["child_generation"],
                        description=f"Parent appears age {parent_age} at child birth",
                    )
            if parent_death and child_birth and child_birth.year > parent_death.year + 1:
                _add_issue(
                    con,
                    issue_type="child_after_parent_death",
                    severity="high",
                    person_id=rel["person_id"],
                    person_name=rel["parent_name"],
                    related_person_id=rel["related_person_id"],
                    related_person_name=rel["child_name"],
                    relationship_id=rel["relationship_id"],
                    generation=rel["child_generation"],
                    description=f"Child birth {rel['child_birth']} is after parent death {rel['parent_death']}",
                )

        for person_id in _ancestor_cycle_nodes(parent_edges):
            person = people.get(person_id)
            _add_issue(
                con,
                issue_type="ancestor_cycle",
                severity="critical",
                person_id=person_id,
                person_name=person["full_name"] if person else "",
                generation=person["generation"] if person else None,
                description="Person participates in a parent/ancestor cycle",
            )

        con.commit()
        return con.execute("SELECT COUNT(*) FROM validation_issue").fetchone()[0]
    finally:
        con.close()


if __name__ == "__main__":
    print(f"Validation issues: {rebuild_validation_issues()}")

