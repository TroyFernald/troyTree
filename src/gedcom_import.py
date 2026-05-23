from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from .date_validation import find_date_issues
from .init_database import connect, initialize_database
from .paths import ORIGINAL_DIR, WORKING_DB


@dataclass
class Event:
    date: str = ""
    place: str = ""


@dataclass
class Individual:
    person_id: str
    full_name: str = ""
    given_name: str = ""
    surname: str = ""
    sex: str = ""
    birth: Event = field(default_factory=Event)
    death: Event = field(default_factory=Event)
    famc: list[str] = field(default_factory=list)
    fams: list[str] = field(default_factory=list)
    source_count: int = 0


@dataclass
class Family:
    family_id: str
    husband_id: str = ""
    wife_id: str = ""
    child_ids: list[str] = field(default_factory=list)


@dataclass
class RawRecord:
    xref: str
    record_type: str
    raw_text: str


def clean_name(value: str) -> str:
    return value.replace("/", "").replace("  ", " ").strip()


def _record_from_lines(lines: list[str]) -> RawRecord | None:
    if not lines:
        return None
    parts = lines[0].split(" ", 2)
    if len(parts) == 3 and parts[0] == "0" and parts[1].startswith("@"):
        return RawRecord(parts[1], parts[2], "\n".join(lines))
    return None


def file_hash(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_gedcom(path=ORIGINAL_DIR / "Troy Tree.ged") -> tuple[dict[str, Individual], dict[str, Family], list[RawRecord]]:
    individuals: dict[str, Individual] = {}
    families: dict[str, Family] = {}
    raw_records: list[RawRecord] = []
    current_indi: Individual | None = None
    current_family: Family | None = None
    current_event: Event | None = None
    current_raw: list[str] = []

    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            parts = line.split(" ", 2)
            if len(parts) < 2:
                continue
            level = int(parts[0])
            tag = parts[1]
            value = parts[2] if len(parts) > 2 else ""

            if level == 0:
                record = _record_from_lines(current_raw)
                if record:
                    raw_records.append(record)
                current_raw = [line]
                current_indi = None
                current_family = None
                current_event = None
                if len(parts) == 3 and value == "INDI":
                    current_indi = Individual(person_id=tag)
                    individuals[tag] = current_indi
                elif len(parts) == 3 and value == "FAM":
                    current_family = Family(family_id=tag)
                    families[tag] = current_family
                continue
            current_raw.append(line)

            if current_indi:
                if level == 1:
                    current_event = None
                    if tag == "NAME":
                        current_indi.full_name = clean_name(value)
                    elif tag == "SEX":
                        current_indi.sex = value
                    elif tag == "BIRT":
                        current_event = current_indi.birth
                    elif tag == "DEAT":
                        current_event = current_indi.death
                    elif tag == "FAMC":
                        current_indi.famc.append(value)
                    elif tag == "FAMS":
                        current_indi.fams.append(value)
                    elif tag == "SOUR":
                        current_indi.source_count += 1
                elif level == 2:
                    if tag == "GIVN":
                        current_indi.given_name = value.strip()
                    elif tag == "SURN":
                        current_indi.surname = value.strip()
                    elif current_event and tag == "DATE":
                        current_event.date = value.strip()
                    elif current_event and tag == "PLAC":
                        current_event.place = value.strip()
                    elif tag == "SOUR":
                        current_indi.source_count += 1
                continue

            if current_family and level == 1:
                if tag == "HUSB":
                    current_family.husband_id = value
                elif tag == "WIFE":
                    current_family.wife_id = value
                elif tag == "CHIL":
                    current_family.child_ids.append(value)

    record = _record_from_lines(current_raw)
    if record:
        raw_records.append(record)

    return individuals, families, raw_records


def create_import_batch(con, path) -> int:
    source_hash = file_hash(path)
    existing = con.execute(
        "SELECT import_batch_id FROM import_batch WHERE source_hash = ? AND source_path = ?",
        (source_hash, str(path)),
    ).fetchone()
    if existing:
        batch_id = existing["import_batch_id"]
        con.execute("DELETE FROM raw_record WHERE import_batch_id = ?", (batch_id,))
        con.execute("DELETE FROM evidence_assertion WHERE import_batch_id = ?", (batch_id,))
        con.execute("DELETE FROM citation WHERE raw_record_id NOT IN (SELECT raw_record_id FROM raw_record)")
        return batch_id
    cur = con.execute(
        """
        INSERT INTO import_batch (
            source_name, source_path, source_hash, source_type, gedcom_version, parser_version, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (path.name, str(path), source_hash, "GEDCOM", "5.5.1", "local-parser-v1", "Imported from Ancestry GEDCOM export"),
    )
    return cur.lastrowid


def source_and_citation(con, batch_id: int, raw_record_id: int, title: str) -> tuple[int, int]:
    source = con.execute(
        "SELECT source_id FROM source WHERE source_title = ? AND source_type = 'GEDCOM import'",
        (title,),
    ).fetchone()
    if source:
        source_id = source["source_id"]
    else:
        cur = con.execute(
            """
            INSERT INTO source (source_title, source_type, source_quality, notes)
            VALUES (?, 'GEDCOM import', 'derivative', ?)
            """,
            (title, f"Created from import batch {batch_id}"),
        )
        source_id = cur.lastrowid
    cur = con.execute(
        """
        INSERT INTO citation (
            source_id, raw_record_id, citation_text, information_type, evidence_type, review_status
        ) VALUES (?, ?, ?, 'unknown', 'unknown', 'imported')
        """,
        (source_id, raw_record_id, f"{title}; raw GEDCOM record {raw_record_id}"),
    )
    return source_id, cur.lastrowid


def insert_assertion(
    con,
    *,
    import_batch_id: int,
    raw_record_id: int,
    citation_id: int,
    subject_type: str,
    subject_id: str,
    person_id: str,
    claim_type: str,
    claim_value: str = "",
    date_text: str = "",
    place_text: str = "",
    confidence_score: int = 40,
    confidence_label: str = "Low confidence",
) -> None:
    con.execute(
        """
        INSERT INTO evidence_assertion (
            import_batch_id, raw_record_id, citation_id, subject_type, subject_id,
            person_id, claim_type, claim_value, date_text, place_text,
            source_quality, information_type, evidence_type, confidence_score,
            confidence_label, review_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'derivative', 'unknown', 'unknown', ?, ?, 'imported')
        """,
        (
            import_batch_id,
            raw_record_id,
            citation_id,
            subject_type,
            subject_id,
            person_id,
            claim_type,
            claim_value,
            date_text,
            place_text,
            confidence_score,
            confidence_label,
        ),
    )


def import_gedcom(path=ORIGINAL_DIR / "Troy Tree.ged") -> tuple[int, int]:
    initialize_database(WORKING_DB)
    individuals, families, raw_records = parse_gedcom(path)

    spouse_names: dict[str, set[str]] = {person_id: set() for person_id in individuals}
    parent_names: dict[str, set[str]] = {person_id: set() for person_id in individuals}
    relationships: list[tuple[str, str, str, str, str]] = []

    for family in families.values():
        spouses = [pid for pid in (family.husband_id, family.wife_id) if pid]
        if len(spouses) == 2:
            left, right = spouses
            spouse_names.setdefault(left, set()).add(individuals.get(right, Individual(right)).full_name)
            spouse_names.setdefault(right, set()).add(individuals.get(left, Individual(left)).full_name)
            relationships.append((family.family_id, left, right, "spouse", ""))
            relationships.append((family.family_id, right, left, "spouse", ""))
        for child_id in family.child_ids:
            for parent_id in spouses:
                parent_names.setdefault(child_id, set()).add(individuals.get(parent_id, Individual(parent_id)).full_name)
                relationships.append((family.family_id, parent_id, child_id, "parent", ""))
                relationships.append((family.family_id, child_id, parent_id, "child", ""))

    with connect(WORKING_DB) as con:
        con.execute("DELETE FROM family_relationships")
        con.execute("DELETE FROM review_task WHERE task_type IN ('citation_gap', 'proof_gap')")
        batch_id = create_import_batch(con, path)
        raw_record_ids: dict[str, int] = {}
        for record in raw_records:
            cur = con.execute(
                """
                INSERT INTO raw_record (import_batch_id, xref, record_type, raw_text, parsed_summary)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    record.xref,
                    record.record_type,
                    record.raw_text,
                    json.dumps({"xref": record.xref, "record_type": record.record_type}),
                ),
            )
            raw_record_ids[record.xref] = cur.lastrowid

        for person in individuals.values():
            issues = find_date_issues(person.birth.date, person.death.date, person_name=person.full_name)
            notes = "; ".join(issue.message for issue in issues)
            existing = con.execute(
                "SELECT relationship_to_root, confidence_status, notes FROM people WHERE person_id = ?",
                (person.person_id,),
            ).fetchone()
            relationship_to_root = existing["relationship_to_root"] if existing else ""
            confidence_status = existing["confidence_status"] if existing else (
                "unsourced" if person.source_count == 0 else "gedcom_imported"
            )
            combined_notes = "; ".join(part for part in [existing["notes"] if existing else "", notes] if part)
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
                    person.person_id,
                    person.full_name,
                    person.given_name,
                    person.surname,
                    person.birth.date,
                    person.birth.place,
                    person.death.date,
                    person.death.place,
                    "; ".join(sorted(name for name in spouse_names.get(person.person_id, set()) if name)),
                    "; ".join(sorted(name for name in parent_names.get(person.person_id, set()) if name)),
                    None,
                    relationship_to_root,
                    person.source_count,
                    confidence_status,
                    combined_notes,
                ),
            )
            raw_record_id = raw_record_ids.get(person.person_id)
            if raw_record_id:
                _, citation_id = source_and_citation(con, batch_id, raw_record_id, f"GEDCOM individual {person.person_id}")
                if person.full_name:
                    insert_assertion(
                        con,
                        import_batch_id=batch_id,
                        raw_record_id=raw_record_id,
                        citation_id=citation_id,
                        subject_type="person",
                        subject_id=person.person_id,
                        person_id=person.person_id,
                        claim_type="name",
                        claim_value=person.full_name,
                    )
                if person.birth.date or person.birth.place:
                    insert_assertion(
                        con,
                        import_batch_id=batch_id,
                        raw_record_id=raw_record_id,
                        citation_id=citation_id,
                        subject_type="person",
                        subject_id=person.person_id,
                        person_id=person.person_id,
                        claim_type="birth",
                        date_text=person.birth.date,
                        place_text=person.birth.place,
                    )
                if person.death.date or person.death.place:
                    insert_assertion(
                        con,
                        import_batch_id=batch_id,
                        raw_record_id=raw_record_id,
                        citation_id=citation_id,
                        subject_type="person",
                        subject_id=person.person_id,
                        person_id=person.person_id,
                        claim_type="death",
                        date_text=person.death.date,
                        place_text=person.death.place,
                    )
        con.executemany(
            """
            INSERT INTO family_relationships (
                family_id, person_id, related_person_id, relationship_type, notes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            relationships,
        )
        for family in families.values():
            raw_record_id = raw_record_ids.get(family.family_id)
            if not raw_record_id:
                continue
            _, citation_id = source_and_citation(con, batch_id, raw_record_id, f"GEDCOM family {family.family_id}")
            spouses = [pid for pid in (family.husband_id, family.wife_id) if pid]
            if len(spouses) == 2:
                insert_assertion(
                    con,
                    import_batch_id=batch_id,
                    raw_record_id=raw_record_id,
                    citation_id=citation_id,
                    subject_type="relationship",
                    subject_id=family.family_id,
                    person_id=spouses[0],
                    claim_type="spouse",
                    claim_value=spouses[1],
                )
            for child_id in family.child_ids:
                for parent_id in spouses:
                    insert_assertion(
                        con,
                        import_batch_id=batch_id,
                        raw_record_id=raw_record_id,
                        citation_id=citation_id,
                        subject_type="relationship",
                        subject_id=family.family_id,
                        person_id=child_id,
                        claim_type="parent_child",
                        claim_value=f"{parent_id}->{child_id}",
                    )
        con.commit()

    return len(individuals), len(families)


if __name__ == "__main__":
    people_count, family_count = import_gedcom()
    print(f"Imported {people_count} GEDCOM individuals and {family_count} families into {WORKING_DB}")
