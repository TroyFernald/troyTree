"""Record agent web-research findings into the research database.

Findings are produced by research agents (live public-web searches) and passed
here as a JSON list. Each finding is upserted into ``web_research_finding`` and,
when it carries claimed facts, mirrored into ``evidence_candidates`` so it shows
up in the existing review reports. Matching ``web_research_target`` rows for the
person are flipped to ``researched`` so the same person is not re-queued.

Findings are clues, not proof. Nothing here is written to ``people`` or to any
conclusion table; human review still decides what gets accepted.

Usage:
    python -m src.record_findings findings.json

Each finding object accepts:
    person_id, person_name, search_query, source_title, source_url, source_site,
    snippet, claimed_facts, confidence_score, confidence_label, agrees, conflicts,
    notes
"""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlparse

from .init_database import connect, initialize_database
from .paths import WORKING_DB


def _site(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def record_findings(findings: list[dict], processed: list[str] | None = None, db_path=WORKING_DB) -> dict:
    """Upsert findings; close targets for everyone in ``processed`` (or, if not
    given, everyone who produced a finding). ``processed`` lets us mark people who
    were researched but yielded nothing, so they are not re-queued forever."""
    initialize_database(db_path)
    stats = {"findings_written": 0, "candidates_written": 0, "targets_closed": 0, "people": set()}
    with connect(db_path) as con:
        for f in findings:
            # agents occasionally emit a nested object in a text field; coerce to text
            f = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                 for k, v in f.items()}
            person_id = f.get("person_id") or ""
            url = f.get("source_url") or ""
            if not person_id or not url:
                continue
            site = f.get("source_site") or _site(url)
            notes = f.get("notes", "")
            if f.get("conflicts"):
                notes = (notes + " | CONFLICT: " + f["conflicts"]).strip(" |")
            con.execute(
                """
                INSERT INTO web_research_finding (
                    person_id, person_name, search_query, source_title, source_type,
                    source_url, source_site, snippet, claimed_facts, confidence_score,
                    confidence_label, review_status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'needs_review', ?)
                ON CONFLICT(person_id, source_url) DO UPDATE SET
                    person_name   = excluded.person_name,
                    search_query  = excluded.search_query,
                    source_title  = excluded.source_title,
                    snippet       = excluded.snippet,
                    claimed_facts = excluded.claimed_facts,
                    confidence_score = excluded.confidence_score,
                    confidence_label = excluded.confidence_label,
                    notes         = excluded.notes
                """,
                (
                    person_id,
                    f.get("person_name", ""),
                    f.get("search_query", ""),
                    f.get("source_title", ""),
                    f.get("source_type", "public web finding"),
                    url,
                    site,
                    f.get("snippet", ""),
                    f.get("claimed_facts", ""),
                    int(f.get("confidence_score", 0) or 0),
                    f.get("confidence_label", "Weak clue only"),
                    notes,
                ),
            )
            stats["findings_written"] += 1
            stats["people"].add(person_id)

            if f.get("claimed_facts"):
                exists = con.execute(
                    "SELECT 1 FROM evidence_candidates WHERE person_id=? AND source_url=?",
                    (person_id, url),
                ).fetchone()
                if not exists:
                    con.execute(
                        """
                        INSERT INTO evidence_candidates (
                            person_id, person_name, source_title, source_type, source_url,
                            source_site, summary, confidence_score, confidence_label,
                            conflicts, date_found, review_status, review_notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'), 'needs_review', ?)
                        """,
                        (
                            person_id,
                            f.get("person_name", ""),
                            f.get("source_title", ""),
                            f.get("source_type", "public web finding"),
                            url,
                            site,
                            f.get("claimed_facts", ""),
                            int(f.get("confidence_score", 0) or 0),
                            f.get("confidence_label", "Weak clue only"),
                            f.get("conflicts", ""),
                            notes,
                        ),
                    )
                    stats["candidates_written"] += 1

        to_close = set(stats["people"]) | set(processed or [])
        for person_id in to_close:
            cur = con.execute(
                "UPDATE web_research_target SET status='researched' WHERE person_id=? AND status='open'",
                (person_id,),
            )
            stats["targets_closed"] += cur.rowcount
        con.commit()

    stats["people"] = len(stats["people"])
    stats["people_processed"] = len(to_close)
    return stats


def ingest_dir(directory: str, db_path=WORKING_DB) -> dict:
    """Bulk-ingest every ``*.json`` chunk file an agent wrote into ``directory``.
    Each file may be a list of findings or a dict with ``findings`` and
    optional ``processed`` (person_ids researched, including empty results)."""
    import glob
    findings: list[dict] = []
    processed: list[str] = []
    files = sorted(glob.glob(os.path.join(directory, "*.json")))
    for fp in files:
        with open(fp, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            findings.extend(data.get("findings", []))
            processed.extend(data.get("processed", []))
        else:
            findings.extend(data)
    stats = record_findings(findings, processed, db_path)
    stats["files"] = len(files)
    return stats


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "findings.json"
    if os.path.isdir(arg):
        print(ingest_dir(arg))
    else:
        with open(arg, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            print(record_findings(data.get("findings", []), data.get("processed")))
        else:
            print(record_findings(data))
