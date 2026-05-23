from __future__ import annotations

import csv
from datetime import date

from .ancestry_person import AncestryPerson
from .date_validation import find_date_issues
from .direct_ancestor_audit import update_direct_ancestor_audit
from .duplicate_detection import find_duplicate_candidates
from .gedcom_import import import_gedcom
from .init_database import connect, initialize_database
from .paths import ORIGINAL_DIR, WORKING_DB, ensure_directories
from .research_queue import TARGET_SOURCES, build_search_terms
from .relationship_validation import rebuild_validation_issues
from .review_tasks import rebuild_review_tasks
from .source_scoring import infer_source_type, score_evidence, source_site
from .web_research import import_web_findings, rebuild_web_research_targets


def read_csv(name: str) -> list[dict]:
    path = ORIGINAL_DIR / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _person_from_row(row: dict) -> AncestryPerson:
    return AncestryPerson(
        person_id=row.get("person_id", ""),
        full_name=row.get("name", ""),
        generation=row.get("generation", ""),
        sex=row.get("sex", ""),
        birth_date=row.get("birth_date", ""),
        birth_place=row.get("birth_place", ""),
        death_date=row.get("death_date", ""),
        death_place=row.get("death_place", ""),
        source_count=int(row.get("ancestry_source_count") or 0),
        source_titles=row.get("ancestry_source_titles", ""),
    )


def import_people(con, rows: list[dict]) -> None:
    for row in rows:
        person = _person_from_row(row)
        date_issues = find_date_issues(person.birth_date, person.death_date, person_name=person.full_name)
        notes = "; ".join(issue.message for issue in date_issues)
        if person.source_count == 0:
            confidence_status = "unsourced"
        elif "Ancestry Family Trees" in person.source_titles:
            confidence_status = "weak_source_only"
        else:
            confidence_status = "needs_review"

        existing = con.execute(
            "SELECT spouse_names, parent_names FROM people WHERE person_id = ?",
            (person.person_id,),
        ).fetchone()
        con.execute(
            """
            INSERT OR REPLACE INTO people (
                person_id, gedcom_id, full_name, given_name, surname, birth_date,
                birth_place, death_date, death_place, spouse_names, parent_names,
                generation, relationship_to_root, source_count, confidence_status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                person.person_id,
                person.gedcom_id,
                person.full_name,
                person.given_name,
                person.surname,
                person.birth_date,
                person.birth_place,
                person.death_date,
                person.death_place,
                existing["spouse_names"] if existing else "",
                existing["parent_names"] if existing else "",
                int(person.generation or 0),
                "direct ancestor",
                person.source_count,
                confidence_status,
                notes,
            ),
        )


def import_evidence(con, rows: list[dict], person_names: dict[str, str]) -> None:
    con.execute("DELETE FROM evidence_candidates")
    for row in rows:
        source_title = row.get("source_title", "")
        source_url = row.get("source_url", "")
        claimed_facts = row.get("claimed_facts", "")
        score, label = score_evidence(
            source_title=source_title,
            source_url=source_url,
            evidence_type=row.get("evidence_type", ""),
            claimed_facts=claimed_facts,
            pilot_confidence=row.get("confidence", ""),
        )
        conflicts = "date conflict" if "conflict" in claimed_facts.lower() else ""
        con.execute(
            """
            INSERT INTO evidence_candidates (
                person_id, person_name, source_title, source_type, source_url, source_site,
                claimed_birth_date, claimed_birth_place, claimed_death_date, claimed_death_place,
                claimed_spouse, claimed_parents, claimed_children, summary, transcription,
                confidence_score, confidence_label, conflicts, date_found, review_status, review_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("person_id", ""),
                person_names.get(row.get("person_id", ""), ""),
                source_title,
                infer_source_type(source_title, source_url, row.get("evidence_type", "")),
                source_url,
                source_site(source_url),
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                claimed_facts,
                "",
                score,
                label,
                conflicts,
                date.today().isoformat(),
                row.get("status", "needs_review") or "needs_review",
                row.get("action", ""),
            ),
        )


def import_queue(con, rows: list[dict], people: list[dict], person_names: dict[str, str]) -> None:
    con.execute("DELETE FROM research_queue")
    people_by_id = {p["person_id"]: p for p in people}
    for row in rows:
        person = people_by_id.get(row.get("person_id", ""), {})
        search_terms = row.get("next_search") or " | ".join(build_search_terms(person))
        con.execute(
            """
            INSERT INTO research_queue (
                person_id, person_name, priority, reason, search_terms, target_sources,
                status, assigned_to, created_date, last_researched_date, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("person_id", ""),
                person_names.get(row.get("person_id", ""), ""),
                int(row.get("priority") or 999),
                row.get("reason", ""),
                search_terms,
                ", ".join(TARGET_SOURCES),
                row.get("status", "open") or "open",
                "",
                date.today().isoformat(),
                "",
                "",
            ),
        )


def import_duplicates(con) -> None:
    con.execute("DELETE FROM duplicate_candidates")
    people = [dict(row) for row in con.execute("SELECT * FROM people").fetchall()]
    for candidate in find_duplicate_candidates(people):
        con.execute(
            """
            INSERT INTO duplicate_candidates (
                left_person_id, right_person_id, left_name, right_name,
                left_birth_date, right_birth_date, left_birth_place, right_birth_place,
                left_death_date, right_death_date, left_death_place, right_death_place,
                left_relationship_to_root, right_relationship_to_root, score, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.left_person_id,
                candidate.right_person_id,
                candidate.left_name,
                candidate.right_name,
                candidate.left_birth_date,
                candidate.right_birth_date,
                candidate.left_birth_place,
                candidate.right_birth_place,
                candidate.left_death_date,
                candidate.right_death_date,
                candidate.left_death_place,
                candidate.right_death_place,
                candidate.left_relationship_to_root,
                candidate.right_relationship_to_root,
                candidate.score,
                candidate.reason,
            ),
        )


def import_pilot_data() -> None:
    ensure_directories()
    initialize_database(WORKING_DB)
    import_gedcom()
    people = read_csv("persons.csv")
    evidence = read_csv("evidence_candidates.csv")
    queue = read_csv("research_queue.csv")
    person_names = {row.get("person_id", ""): row.get("name", "") for row in people}

    with connect(WORKING_DB) as con:
        import_people(con, people)
        import_evidence(con, evidence, person_names)
        import_queue(con, queue, people, person_names)
        import_duplicates(con)
        con.commit()
    update_direct_ancestor_audit()
    rebuild_validation_issues()
    rebuild_web_research_targets()
    import_web_findings()
    rebuild_review_tasks()


if __name__ == "__main__":
    import_pilot_data()
    print(f"Imported pilot data into {WORKING_DB}")
