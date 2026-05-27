"""Prioritized batch runner for public-web ancestor research.

The research loop in this project is agent-driven and deliberately
human-in-the-loop. This module is the front of that loop: it turns the open
``web_research_target`` rows into a prioritized worklist of *people* and slices
them into self-contained batch assignment files that a research agent can pick
up and work one at a time.

The loop:

    1.  python -m src.research_batch plan 60          # write prioritized batches
    2.  a research agent reads data/exports/research_batches/batch_001.json,
        searches PUBLIC sources only, writes findings into data/exports/findings/
    3.  python -m src.record_findings data/exports/findings   # ingest the chunks
    4.  python -m src.research_batch status                   # see what's left

Prioritization (highest first) follows the project's research priorities:
weak/no-source direct ancestors, generations 4-8, the New England / Maritime
core (Maine, New Hampshire, Massachusetts, Nova Scotia), and the key surnames
(Fernald, Bagley, Meserve, Fuller, McKay, ...). Those are already encoded in
``direct_ancestor_audit.priority``; this module surfaces them and adds optional
hard filters.

Rules baked into every assignment file: public sources only, never use an
Ancestry/Newspapers.com login or scrape account-gated pages, and every finding
is a clue for human review — nothing is written to ``people``.
"""

from __future__ import annotations

import json
import sys

from .direct_ancestor_audit import PRIORITY_PLACES, PRIORITY_SURNAMES
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import is_living
from .research_queue import TARGET_SOURCES, build_search_terms

BATCH_DIR = EXPORTS_DIR / "research_batches"
WORKLIST_PATH = EXPORTS_DIR / "research_worklist.json"

PUBLIC_SOURCE_RULES = [
    "Search PUBLIC sources only: FamilySearch, WikiTree, Find a Grave, Internet "
    "Archive, Google Books, HathiTrust, Chronicling America, published town/county "
    "histories, and free vital/census indexes.",
    "NEVER log in to Ancestry or Newspapers.com and never scrape account-gated "
    "pages. If a fact is only visible behind a paywall/login, skip it.",
    "Every finding is a CLUE for human review, not proof. Do not assert anything "
    "as fact and do not merge people on name alone.",
    "Record conflicts explicitly (e.g. a date that disagrees with the tree) in the "
    "'conflicts' field — conflicts are valuable.",
    "Prefer record-based sources (census, vital, probate, cemetery) over other "
    "people's trees. Tree-only hits are weak clues.",
]

FINDING_SCHEMA = {
    "person_id": "the person_id from this batch (required)",
    "person_name": "name as searched",
    "search_query": "the query that found it",
    "source_title": "title of the page/record",
    "source_url": "public URL (required; no login URLs)",
    "source_type": "e.g. census, vital record, Find a Grave memorial, town history, tree",
    "snippet": "short quote/snippet from the source",
    "claimed_facts": "what the source claims (dates, places, parents, spouse, etc.)",
    "confidence_score": "0-100 integer; record-based high, tree-only low",
    "confidence_label": "Weak clue only / Low / Medium / Medium-high / High confidence",
    "agrees": "facts that agree with the current tree",
    "conflicts": "facts that conflict with the current tree",
    "notes": "anything else worth a reviewer's attention",
}


def build_worklist(
    limit: int = 200,
    *,
    gen_min: int | None = None,
    gen_max: int | None = None,
    regions: list[str] | None = None,
    surnames: set[str] | None = None,
    weak_only: bool = False,
    include_living: bool = False,
    db_path=WORKING_DB,
) -> list[dict]:
    """One prioritized row per person with an open research target.

    Defaults pull the whole open worklist ordered by priority; the keyword
    filters let a caller carve out a focused batch (e.g. gens 4-8, weak-source
    only) without changing the priority ordering.
    """
    with connect(db_path) as con:
        rows = con.execute(
            """
            SELECT t.person_id, t.person_name,
                   MIN(t.generation) AS generation, MIN(t.priority) AS priority,
                   p.surname, p.birth_date, p.birth_place, p.death_date, p.death_place,
                   p.spouse_names, p.parent_names, p.confidence_status, p.source_count,
                   (SELECT COUNT(*) FROM web_research_finding f WHERE f.person_id = t.person_id) AS n_findings
            FROM web_research_target t
            JOIN people p ON p.person_id = t.person_id
            WHERE t.status = 'open'
            GROUP BY t.person_id
            ORDER BY MIN(t.priority) ASC, n_findings ASC, MIN(t.generation) ASC, t.person_name
            """
        ).fetchall()

    regions = regions or []
    out: list[dict] = []
    for r in rows:
        person = dict(r)
        gen = person["generation"]
        if not include_living and is_living(person["birth_date"], person["death_date"], gen):
            continue
        if gen_min is not None and (gen is None or gen < gen_min):
            continue
        if gen_max is not None and (gen is None or gen > gen_max):
            continue
        if weak_only and (person["confidence_status"] not in ("unsourced", "weak_source_only")
                          and (person["source_count"] or 0) > 1):
            continue
        if surnames and (person["surname"] or "") not in surnames:
            continue
        if regions:
            place = f"{person['birth_place'] or ''} {person['death_place'] or ''}"
            if not any(region.lower() in place.lower() for region in regions):
                continue
        # build_search_terms keys on full_name/name; the worklist row uses person_name
        person["suggested_searches"] = build_search_terms(
            {**person, "full_name": person["person_name"]}
        )[:8]
        person["target_sources"] = TARGET_SOURCES
        out.append(person)
        if len(out) >= limit:
            break
    return out


def write_batches(people: list[dict], batch_size: int = 12, out_dir=BATCH_DIR) -> dict:
    """Split a worklist into numbered assignment files plus an INSTRUCTIONS.md."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("batch_*.json"):
        stale.unlink()
    batches = [people[i:i + batch_size] for i in range(0, len(people), batch_size)]
    for n, batch in enumerate(batches, start=1):
        payload = {
            "batch": n,
            "of": len(batches),
            "rules": PUBLIC_SOURCE_RULES,
            "finding_schema": FINDING_SCHEMA,
            "write_findings_to": "data/exports/findings/batch_%03d.json" % n,
            "people": batch,
        }
        (out_dir / f"batch_{n:03d}.json").write_text(
            json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8"
        )
    WORKLIST_PATH.write_text(json.dumps(people, indent=1, ensure_ascii=False), encoding="utf-8")
    _write_instructions(out_dir, len(people), len(batches), batch_size)
    return {"people": len(people), "batches": len(batches), "dir": str(out_dir)}


def _write_instructions(out_dir, n_people: int, n_batches: int, batch_size: int) -> None:
    lines = [
        "# Research batch assignments",
        "",
        f"{n_people} people across {n_batches} batches ({batch_size} per batch), "
        "ordered by research priority (weakest-sourced, highest-value ancestors first).",
        "",
        "## How to work a batch",
        "",
        "1. Open `batch_NNN.json`. For each person, run public-web searches using the "
        "`suggested_searches` (and your own better queries).",
        "2. Write the findings you trust into the file named in `write_findings_to` as a "
        "JSON object: `{ \"findings\": [...], \"processed\": [person_id, ...] }`. List a "
        "person in `processed` even if they yielded nothing, so they are not re-queued.",
        "3. Each finding object uses the fields in `finding_schema`.",
        "4. Ingest: `python -m src.record_findings data/exports/findings`.",
        "",
        "## Rules (non-negotiable)",
        "",
    ]
    lines += [f"- {rule}" for rule in PUBLIC_SOURCE_RULES]
    (out_dir / "INSTRUCTIONS.md").write_text("\n".join(lines), encoding="utf-8")


def status(db_path=WORKING_DB) -> dict:
    """Progress snapshot of the research sweep."""
    with connect(db_path) as con:
        def scalar(sql):
            return con.execute(sql).fetchone()[0]

        by_gen = [
            dict(r)
            for r in con.execute(
                """
                SELECT generation,
                       SUM(status = 'open') AS open_targets,
                       COUNT(DISTINCT CASE WHEN status = 'open' THEN person_id END) AS people_remaining
                FROM web_research_target
                GROUP BY generation
                HAVING people_remaining > 0
                ORDER BY generation
                """
            )
        ]
        return {
            "open_targets": scalar("SELECT COUNT(*) FROM web_research_target WHERE status='open'"),
            "researched_targets": scalar(
                "SELECT COUNT(*) FROM web_research_target WHERE status='researched'"
            ),
            "people_remaining": scalar(
                "SELECT COUNT(DISTINCT person_id) FROM web_research_target WHERE status='open'"
            ),
            "people_done": scalar(
                "SELECT COUNT(DISTINCT person_id) FROM web_research_target WHERE status='researched'"
            ),
            "findings_recorded": scalar("SELECT COUNT(*) FROM web_research_finding"),
            "evidence_candidates": scalar("SELECT COUNT(*) FROM evidence_candidates"),
            "remaining_by_generation": by_gen,
        }


def _print_status(s: dict) -> None:
    print(f"open targets:        {s['open_targets']:>7}")
    print(f"researched targets:  {s['researched_targets']:>7}")
    print(f"people remaining:    {s['people_remaining']:>7}")
    print(f"people researched:   {s['people_done']:>7}")
    print(f"findings recorded:   {s['findings_recorded']:>7}")
    print("people remaining by generation:")
    for row in s["remaining_by_generation"]:
        print(f"  gen {str(row['generation']):>3}: {row['people_remaining']:>5} people")


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        _print_status(status())
        return
    if cmd == "plan":
        limit = int(argv[1]) if len(argv) > 1 else 60
        # default focus: weak-source ancestors in generations 4-8
        people = build_worklist(limit=limit, gen_min=4, gen_max=8, weak_only=True)
        if not people:  # fall back to the full priority order if the focus is exhausted
            people = build_worklist(limit=limit)
        result = write_batches(people)
        print(f"Wrote {result['batches']} batches ({result['people']} people) to {result['dir']}")
        print(f"Then: python -m src.record_findings data/exports/findings")
        return
    print(f"Unknown command: {cmd!r}. Use 'plan [N]' or 'status'.", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
