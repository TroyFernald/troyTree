"""Ingest vision-transcription results (data/exports/vision_findings/*.json) into
the database: store each transcription on its media_object, and create review-
ready evidence_candidates rows from the extracted facts. Documents the agents
flagged as false matches (Ancestry OCR mis-links) are marked and not turned into
evidence.
"""

from __future__ import annotations

import glob
import json
import os

from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB

VISION_DIR = EXPORTS_DIR / "vision_findings"
FALSE_HINTS = ("false match", "false-match", "no lenentine", "mis-tagged", "mistagged",
               "not a match", "no relevant", "appears mis", "contains no", "unrelated",
               "misattributed", "mislink", "mis-link", "different person", "not the target",
               "probable false", "likely false", "wrong person", "chronological false")


def _conf(legibility: str) -> tuple[int, str]:
    l = (legibility or "").lower()
    if "good" in l:
        return 72, "Medium-high confidence"
    if "poor" in l:
        return 40, "Low confidence"
    return 55, "Medium confidence"


def ingest(db_path=WORKING_DB) -> dict:
    stats = {"docs": 0, "transcribed": 0, "false_matches": 0, "evidence_rows": 0, "people": set()}
    with connect(db_path) as con:
        for fp in sorted(glob.glob(str(VISION_DIR / "*.json"))):
            data = json.load(open(fp, encoding="utf-8"))
            name = data.get("person_name", "")
            row = con.execute("SELECT person_id FROM people WHERE lower(full_name)=lower(?)", (name,)).fetchone()
            person_id = row["person_id"] if row else None
            for d in data.get("docs", []):
                stats["docs"] += 1
                mid = d.get("media_id")
                trans = (d.get("transcription") or "").strip()
                facts = (d.get("extracted_facts") or "").strip()
                blob = f"{d.get('doc_type','')} {d.get('legibility','')} {facts} {trans}".lower()
                is_false = any(h in blob for h in FALSE_HINTS) or not facts
                mrow = con.execute("SELECT file_path FROM media_object WHERE media_id=?", (mid,)).fetchone()
                file_path = mrow["file_path"] if mrow else ""
                con.execute(
                    "UPDATE media_object SET ocr_text=?, ocr_status=? WHERE media_id=?",
                    (trans, "vision_nomatch" if is_false else "vision", mid))
                if is_false:
                    stats["false_matches"] += 1
                    # flag the (likely wrong) link for human review and remove any
                    # evidence row a prior, looser run may have created for it
                    con.execute(
                        "UPDATE media_person_link SET link_type='review_false_match' WHERE media_id=? AND person_id=?",
                        (mid, person_id))
                    if person_id and file_path:
                        con.execute(
                            "DELETE FROM evidence_candidates WHERE person_id=? AND source_url=? "
                            "AND source_site='local document (vision transcription)'",
                            (person_id, file_path))
                    continue
                stats["transcribed"] += 1
                if not person_id:
                    continue
                score, label = _conf(d.get("legibility", ""))
                exists = con.execute(
                    "SELECT 1 FROM evidence_candidates WHERE person_id=? AND source_url=?",
                    (person_id, file_path)).fetchone()
                if not exists:
                    con.execute(
                        """INSERT INTO evidence_candidates
                           (person_id, person_name, source_title, source_type, source_url, source_site,
                            summary, transcription, confidence_score, confidence_label, date_found,
                            review_status, review_notes)
                           VALUES (?,?,?,?,?,?,?,?,?,?,date('now'),'needs_review',?)""",
                        (person_id, name, d.get("doc_type", "document"), "primary record (vision OCR)",
                         file_path, "local document (vision transcription)", facts, trans, score, label,
                         f"legibility: {d.get('legibility','')}"))
                    stats["evidence_rows"] += 1
                    stats["people"].add(person_id)
        con.commit()
    stats["people"] = len(stats["people"])
    return stats


if __name__ == "__main__":
    print(ingest())
