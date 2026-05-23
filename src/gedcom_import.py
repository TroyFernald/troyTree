from __future__ import annotations

from dataclasses import dataclass, field

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


def clean_name(value: str) -> str:
    return value.replace("/", "").replace("  ", " ").strip()


def parse_gedcom(path=ORIGINAL_DIR / "Troy Tree.ged") -> tuple[dict[str, Individual], dict[str, Family]]:
    individuals: dict[str, Individual] = {}
    families: dict[str, Family] = {}
    current_indi: Individual | None = None
    current_family: Family | None = None
    current_event: Event | None = None

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

    return individuals, families


def import_gedcom(path=ORIGINAL_DIR / "Troy Tree.ged") -> tuple[int, int]:
    initialize_database(WORKING_DB)
    individuals, families = parse_gedcom(path)

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
        con.executemany(
            """
            INSERT INTO family_relationships (
                family_id, person_id, related_person_id, relationship_type, notes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            relationships,
        )
        con.commit()

    return len(individuals), len(families)


if __name__ == "__main__":
    people_count, family_count = import_gedcom()
    print(f"Imported {people_count} GEDCOM individuals and {family_count} families into {WORKING_DB}")

