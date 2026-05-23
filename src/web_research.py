from __future__ import annotations

import sqlite3

import yaml

from .init_database import connect, initialize_database
from .paths import CONFIG_DIR, WORKING_DB
from .research_queue import build_search_terms
from .source_scoring import infer_source_type, score_evidence, source_site


def suggested_public_searches(person: dict) -> list[str]:
    return build_search_terms(person)


def load_seed_findings(path=CONFIG_DIR / "web_research_seeds.yaml") -> list[dict]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("findings", [])


def import_web_findings(
    db_path=WORKING_DB,
    seed_path=CONFIG_DIR / "web_research_seeds.yaml",
) -> int:
    initialize_database(db_path)
    findings = load_seed_findings(seed_path)
    with connect(db_path) as con:
        for finding in findings:
            source_title = finding.get("source_title", "")
            source_url = finding.get("source_url", "")
            claimed_facts = finding.get("claimed_facts", "")
            source_type = infer_source_type(source_title, source_url, "public web finding")
            score, label = score_evidence(
                source_title=source_title,
                source_url=source_url,
                evidence_type=source_type,
                claimed_facts=claimed_facts,
                pilot_confidence="medium",
            )
            if "Ancestry public profile" in source_title:
                score = min(score, 45)
                label = "Low confidence"
            con.execute(
                """
                INSERT INTO web_research_finding (
                    person_id, person_name, search_query, source_title, source_type,
                    source_url, source_site, snippet, claimed_facts, confidence_score,
                    confidence_label, review_status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'needs_review', ?)
                ON CONFLICT(person_id, source_url) DO UPDATE SET
                    person_name = excluded.person_name,
                    search_query = excluded.search_query,
                    source_title = excluded.source_title,
                    source_type = excluded.source_type,
                    source_site = excluded.source_site,
                    snippet = excluded.snippet,
                    claimed_facts = excluded.claimed_facts,
                    confidence_score = excluded.confidence_score,
                    confidence_label = excluded.confidence_label,
                    notes = excluded.notes
                """,
                (
                    finding.get("person_id", ""),
                    finding.get("person_name", ""),
                    finding.get("search_query", ""),
                    source_title,
                    source_type,
                    source_url,
                    source_site(source_url),
                    finding.get("snippet", ""),
                    claimed_facts,
                    score,
                    label,
                    finding.get("notes", ""),
                ),
            )
            existing = con.execute(
                """
                SELECT evidence_id
                FROM evidence_candidates
                WHERE person_id = ? AND source_url = ?
                """,
                (finding.get("person_id", ""), source_url),
            ).fetchone()
            if not existing:
                con.execute(
                    """
                    INSERT INTO evidence_candidates (
                        person_id, person_name, source_title, source_type, source_url,
                        source_site, summary, confidence_score, confidence_label,
                        conflicts, date_found, review_status, review_notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'), 'needs_review', ?)
                    """,
                    (
                        finding.get("person_id", ""),
                        finding.get("person_name", ""),
                        source_title,
                        source_type,
                        source_url,
                        source_site(source_url),
                        claimed_facts or finding.get("snippet", ""),
                        score,
                        label,
                        "date conflict" if "conflict" in finding.get("notes", "").lower() else "",
                        finding.get("notes", ""),
                    ),
                )
        con.commit()
        return con.execute("SELECT COUNT(*) FROM web_research_finding").fetchone()[0]


def rebuild_web_research_targets(db_path=WORKING_DB, max_generation: int | None = None) -> int:
    initialize_database(db_path)
    with connect(db_path) as con:
        con.execute("DELETE FROM web_research_target")
        query = """
            SELECT daa.*, p.full_name, p.surname, p.spouse_names
            FROM direct_ancestor_audit daa
            JOIN people p ON p.person_id = daa.person_id
            WHERE daa.generation > 0
        """
        params: tuple = ()
        if max_generation is not None:
            query += " AND daa.generation <= ?"
            params = (max_generation,)
        query += " ORDER BY daa.priority, daa.generation, daa.person_name"

        for row in con.execute(query, params):
            person = dict(row)
            reason = person.get("audit_flags") or "direct ancestor public web research"
            searches = build_search_terms(
                {
                    "full_name": person["person_name"],
                    "birth_date": person["birth_date"] or "",
                    "death_date": person["death_date"] or "",
                    "birth_place": person["birth_place"] or "",
                    "surname": person["surname"] or "",
                    "spouse_names": person["spouse_names"] or "",
                }
            )
            for search in searches[:10]:
                con.execute(
                    """
                    INSERT OR IGNORE INTO web_research_target (
                        person_id, person_name, generation, priority, reason,
                        search_query, target_sources, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
                    """,
                    (
                        person["person_id"],
                        person["person_name"],
                        person["generation"],
                        person["priority"],
                        reason,
                        search,
                        "FamilySearch; WikiTree; Find a Grave; Internet Archive; Google Books; town histories; county histories; census indexes",
                    ),
                )
        con.commit()
        return con.execute("SELECT COUNT(*) FROM web_research_target").fetchone()[0]


if __name__ == "__main__":
    print(f"Web research targets: {rebuild_web_research_targets()}")
    print(f"Web research findings: {import_web_findings()}")
