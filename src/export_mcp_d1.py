"""Export a redacted slice of the research database as a Cloudflare D1 seed file.

Produces ``data/exports/mcp_seed.sql`` containing CREATE TABLE + INSERT statements
for just what the MCP server needs to answer questions: people, parent/spouse
links, research findings, and notable flags. Living people are omitted entirely
(same privacy rule as the website), and any link/finding that references a living
person is dropped — so nothing about the living leaks through the AI server.

    python -m src.export_mcp_d1
Then import into D1:
    wrangler d1 execute troytree --file=../data/exports/mcp_seed.sql --remote
"""

from __future__ import annotations

from .ancestral_sides import compute_sides
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import is_living

OUT_PATH = EXPORTS_DIR / "mcp_seed.sql"

SCHEMA = """\
DROP TABLE IF EXISTS people;
DROP TABLE IF EXISTS rel;
DROP TABLE IF EXISTS finding;
DROP TABLE IF EXISTS notable;
CREATE TABLE people (person_id TEXT PRIMARY KEY, full_name TEXT, surname TEXT, birth_date TEXT,
  birth_place TEXT, death_date TEXT, death_place TEXT, generation INTEGER, relationship_to_root TEXT,
  spouse_names TEXT, parent_names TEXT, side TEXT);
CREATE TABLE rel (parent_id TEXT, child_id TEXT, kind TEXT);
CREATE TABLE finding (person_id TEXT, person_name TEXT, source_title TEXT, source_type TEXT,
  snippet TEXT, claimed_facts TEXT, notes TEXT);
CREATE TABLE notable (person_id TEXT, person_name TEXT, category TEXT, notable_reason TEXT);
CREATE INDEX idx_people_name ON people(full_name);
CREATE INDEX idx_rel_child ON rel(child_id);
CREATE INDEX idx_rel_parent ON rel(parent_id);
CREATE INDEX idx_finding_person ON finding(person_id);
"""


def _q(v) -> str:
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''") + "'"


def build(db_path=WORKING_DB) -> dict:
    with connect(db_path) as con:
        sides, side_labels, _ = compute_sides(con)
        living: set[str] = set()
        people_rows = []
        for r in con.execute(
            "SELECT person_id, full_name, surname, birth_date, birth_place, death_date, death_place, "
            "generation, relationship_to_root, spouse_names, parent_names FROM people"
        ):
            if is_living(r["birth_date"], r["death_date"], r["generation"]):
                living.add(r["person_id"])
                continue
            side = ", ".join(side_labels.get(k, k) for k in sides.get(r["person_id"], []))
            people_rows.append((r["person_id"], r["full_name"], r["surname"], r["birth_date"],
                                r["birth_place"], r["death_date"], r["death_place"], r["generation"],
                                r["relationship_to_root"], r["spouse_names"], r["parent_names"], side))

        rel_rows = []
        for r in con.execute(
            "SELECT person_id, related_person_id, relationship_type FROM family_relationships "
            "WHERE relationship_type IN ('parent','spouse')"
        ):
            a, b, kind = r["person_id"], r["related_person_id"], r["relationship_type"]
            if a in living or b in living:
                continue
            # family_relationships stores (parent=person_id, child=related_person_id) for 'parent'
            rel_rows.append((a, b, kind))

        find_rows = []
        for r in con.execute(
            "SELECT person_id, person_name, source_title, source_type, snippet, claimed_facts, notes "
            "FROM web_research_finding"
        ):
            if r["person_id"] in living:
                continue
            find_rows.append((r["person_id"], r["person_name"], r["source_title"], r["source_type"],
                              (r["snippet"] or "")[:500], (r["claimed_facts"] or "")[:500], r["notes"]))

        notable_rows = []
        for r in con.execute(
            "SELECT person_id, person_name, category, notable_reason FROM notable_person_candidate"
        ):
            if r["person_id"] in living:
                continue
            notable_rows.append((r["person_id"], r["person_name"], r["category"], r["notable_reason"]))

    def insert(table, cols, rows):
        out = []
        for i in range(0, len(rows), 200):                       # batch to keep statements reasonable
            chunk = rows[i:i + 200]
            vals = ",\n".join("(" + ",".join(_q(v) for v in row) + ")" for row in chunk)
            out.append(f"INSERT INTO {table} ({cols}) VALUES\n{vals};")
        return "\n".join(out)

    sql = [SCHEMA,
           insert("people", "person_id,full_name,surname,birth_date,birth_place,death_date,death_place,"
                  "generation,relationship_to_root,spouse_names,parent_names,side", people_rows),
           insert("rel", "parent_id,child_id,kind", rel_rows),
           insert("finding", "person_id,person_name,source_title,source_type,snippet,claimed_facts,notes", find_rows),
           insert("notable", "person_id,person_name,category,notable_reason", notable_rows)]
    OUT_PATH.write_text("\n\n".join(sql), encoding="utf-8")
    return {"people": len(people_rows), "rel": len(rel_rows), "findings": len(find_rows),
            "notable": len(notable_rows), "living_excluded": len(living), "out": str(OUT_PATH)}


if __name__ == "__main__":
    print(build())
