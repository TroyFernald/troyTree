"""Drive a large autonomous public-web research sweep.

``export_worklist`` writes the top-N un-researched direct ancestors (one row per
person, with the facts an agent needs) to a JSON file. Research agents read a
slice of that file by index, search public sources, and write findings chunk
files into ``data/exports/findings/``. ``src.record_findings ingest_dir`` then
loads every chunk into the database.

    python -m src.research_sweep 200        # export top 200 to the worklist

Worklist entries are ordered by priority, then fewest existing findings, then
generation, so the weakest-sourced, highest-value ancestors come first.
"""

from __future__ import annotations

import json
import sys

from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB

WORKLIST_PATH = EXPORTS_DIR / "research_worklist.json"


def export_worklist(limit: int = 200, db_path=WORKING_DB) -> int:
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT t.person_id, t.person_name,
                   MIN(t.generation) AS generation, MIN(t.priority) AS priority,
                   p.birth_date, p.birth_place, p.death_date, p.death_place,
                   p.spouse_names, p.parent_names, p.confidence_status,
                   (SELECT COUNT(*) FROM web_research_finding f WHERE f.person_id=t.person_id) AS n_findings
            FROM web_research_target t
            JOIN people p ON p.person_id = t.person_id
            WHERE t.status = 'open'
            GROUP BY t.person_id
            ORDER BY MIN(t.priority) ASC, n_findings ASC, MIN(t.generation) ASC, t.person_name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    worklist = [dict(r) for r in rows]
    WORKLIST_PATH.write_text(json.dumps(worklist, indent=1), encoding="utf-8")
    return len(worklist)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    count = export_worklist(n)
    print(f"Wrote {count} people to {WORKLIST_PATH}")
