"""Generate a per-ancestor evidence packet: a readable Markdown profile pulling
together everything we know and have found for a person — profile facts, parents
and spouse, photos, transcribed documents, military service, web findings,
validation issues, and any flagged mis-linked media.

    python -m src.evidence_packet              # all ancestors with evidence
    python -m src.evidence_packet @I...@        # one person by id

Packets are written to data/exports/packets/ with an index.md.
"""

from __future__ import annotations

import os
import re
import sys

from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB

PACKET_DIR = EXPORTS_DIR / "packets"


def _slug(name: str, pid: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (name or "person").lower()).strip("_")[:50]
    return f"{s}_{re.sub(r'[^0-9]', '', pid)[-6:]}"


def _section(title, lines):
    return f"\n## {title}\n\n" + ("\n".join(lines) if lines else "_none_") + "\n"


def build_packet(con, person) -> str:
    pid = person["person_id"]
    md = [f"# {person['full_name']}", ""]
    g = person["generation"]
    rel = person["relationship_to_root"]
    md.append(f"*Generation {g if g is not None else '—'}"
              + (f" · {rel}" if rel else "") + f" · `{pid}`*")
    facts = []
    for label, col in [("Born", "birth_date"), ("Birthplace", "birth_place"),
                       ("Died", "death_date"), ("Death place", "death_place"),
                       ("Spouse(s)", "spouse_names"), ("Parents", "parent_names"),
                       ("Confidence", "confidence_status")]:
        if person[col]:
            facts.append(f"- **{label}:** {person[col]}")
    md.append(_section("Profile", facts))

    photos = con.execute(
        "SELECT m.file_name FROM media_object m JOIN media_person_link l ON l.media_id=m.media_id "
        "WHERE l.person_id=? AND m.kind='photo' AND l.link_type!='review_false_match' ORDER BY m.file_name",
        (pid,)).fetchall()
    md.append(_section(f"Photos ({len(photos)})", [f"- {r['file_name']}" for r in photos]))

    docs = con.execute(
        "SELECT m.file_name, m.ocr_status, m.ocr_text, m.caption FROM media_object m "
        "JOIN media_person_link l ON l.media_id=m.media_id "
        "WHERE l.person_id=? AND m.kind='document' AND l.link_type!='review_false_match' "
        "ORDER BY m.media_id", (pid,)).fetchall()
    doc_lines = []
    for r in docs:
        txt = (r["ocr_text"] or "").strip()
        if txt and r["ocr_status"] in ("vision", "done"):
            snippet = txt if len(txt) < 700 else txt[:700] + " …"
            doc_lines.append(f"- **{r['file_name']}**\n  > " + snippet.replace("\n", "\n  > "))
        else:
            doc_lines.append(f"- {r['file_name']} _(not transcribed)_")
    md.append(_section(f"Documents ({len(docs)})", doc_lines))

    ev = con.execute(
        "SELECT source_title, source_site, summary, confidence_label FROM evidence_candidates "
        "WHERE person_id=? ORDER BY confidence_score DESC", (pid,)).fetchall()
    ev_lines = [f"- **{r['source_title']}** [{r['confidence_label']}] — {(r['summary'] or '')[:300]}"
                for r in ev]
    md.append(_section(f"Extracted evidence ({len(ev)})", ev_lines))

    mil = con.execute(
        "SELECT person_name, claimed_facts, confidence_label, source_title FROM web_research_finding "
        "WHERE person_id=? AND (lower(claimed_facts) LIKE '%regiment%' OR lower(claimed_facts) LIKE '%pension%' "
        "OR lower(claimed_facts) LIKE '%private%' OR lower(claimed_facts) LIKE '%militia%' OR lower(claimed_facts) LIKE '%soldier%' "
        "OR lower(source_title) LIKE '%dar%' OR lower(claimed_facts) LIKE '%corporal%' OR lower(claimed_facts) LIKE '%matross%')",
        (pid,)).fetchall()
    md.append(_section("Military service", [f"- [{r['confidence_label']}] {r['claimed_facts']}" for r in mil]))

    findings = con.execute(
        "SELECT source_title, source_site, claimed_facts, confidence_label FROM web_research_finding "
        "WHERE person_id=? ORDER BY confidence_score DESC", (pid,)).fetchall()
    md.append(_section(f"Web findings ({len(findings)})",
                       [f"- **{r['source_site']}** [{r['confidence_label']}]: {(r['claimed_facts'] or '')[:200]}"
                        for r in findings]))

    issues = con.execute(
        "SELECT issue_type, severity, description FROM validation_issue WHERE person_id=?", (pid,)).fetchall()
    flagged = con.execute(
        "SELECT m.file_name FROM media_object m JOIN media_person_link l ON l.media_id=m.media_id "
        "WHERE l.person_id=? AND l.link_type='review_false_match'", (pid,)).fetchall()
    review = [f"- ⚠️ [{r['severity']}] {r['issue_type']}: {r['description']}" for r in issues]
    review += [f"- ⚠️ mis-linked document (review): {r['file_name']}" for r in flagged]
    md.append(_section("Review flags", review))
    return "\n".join(md)


def generate(target_id=None, db_path=WORKING_DB) -> dict:
    PACKET_DIR.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as con:
        if target_id:
            people = con.execute("SELECT * FROM people WHERE person_id=?", (target_id,)).fetchall()
        else:
            # everyone who has any media, evidence, or finding
            people = con.execute(
                """SELECT DISTINCT p.* FROM people p WHERE p.person_id IN (
                       SELECT person_id FROM media_person_link
                       UNION SELECT person_id FROM evidence_candidates
                       UNION SELECT person_id FROM web_research_finding)
                   ORDER BY p.generation IS NULL, p.generation, p.full_name""").fetchall()
        index = ["# Evidence Packets\n", f"_{len(people)} ancestors with evidence_\n"]
        for person in people:
            md = build_packet(con, person)
            slug = _slug(person["full_name"], person["person_id"])
            (PACKET_DIR / f"{slug}.md").write_text(md, encoding="utf-8")
            g = person["generation"]
            index.append(f"- [{person['full_name']}]({slug}.md) — gen {g if g is not None else '—'}")
        (PACKET_DIR / "index.md").write_text("\n".join(index), encoding="utf-8")
    return {"packets": len(people), "dir": str(PACKET_DIR)}


if __name__ == "__main__":
    print(generate(sys.argv[1] if len(sys.argv) > 1 else None))
