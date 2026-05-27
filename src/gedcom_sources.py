"""Normalize the GEDCOM's real source layer.

The lightweight import in ``gedcom_import`` only *counts* ``SOUR`` lines per
person and creates one synthetic stub source per raw record. It throws away the
actual bibliographic detail the GEDCOM carries:

* top-level ``0 @S..@ SOUR`` records — TITL / AUTH / PUBL / _APID / REPO / NOTE
* top-level ``0 @R..@ REPO`` repository records
* inline ``n SOUR @S..@`` citations under each person/family, with the specific
  ``PAGE`` locator, ``DATA``/``TEXT`` transcript, ``WWW`` link, and ``QUAY``
  credibility, attributed to the event they document (BIRT, DEAT, MARR, …).

This module parses all of that into the normalized ``repository``, ``source``,
and ``citation`` tables so a person's actual cited sources (a census page, a
death index entry, a Find a Grave memorial) can be reviewed and shown in the
evidence packet.

It is non-destructive to the synthetic stubs: real sources are tagged
``source_type = 'GEDCOM source record'`` and carry the GEDCOM ``@S..@`` xref, so
a re-run cleanly replaces only its own rows.

    python -m src.gedcom_sources            # parse default Troy Tree.ged

Findings here are imported claims, not proof — nothing is written to ``people``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import sys

from .init_database import connect, initialize_database
from .paths import ORIGINAL_DIR, WORKING_DB

REAL_SOURCE_TYPE = "GEDCOM source record"

# GEDCOM QUAY (certainty) value -> our information_type label
QUAY_INFO = {"3": "primary", "2": "secondary", "1": "questionable", "0": "unreliable"}


@dataclass
class Node:
    """One GEDCOM line plus its nested lines."""

    tag: str
    value: str = ""
    xref: str | None = None
    children: list["Node"] = field(default_factory=list)

    def child(self, tag: str) -> "Node | None":
        return next((c for c in self.children if c.tag == tag), None)

    def child_value(self, tag: str) -> str:
        c = self.child(tag)
        return c.value if c else ""


def _parse_line(line: str) -> tuple[int, str, str, str | None]:
    parts = line.split(" ", 2)
    level = int(parts[0])
    if len(parts) == 1:
        return level, "", "", None
    # "0 @S1@ SOUR" — second token is an xref, third is the record tag
    if level == 0 and parts[1].startswith("@"):
        tag = parts[2] if len(parts) > 2 else ""
        return level, tag, "", parts[1]
    tag = parts[1]
    value = parts[2] if len(parts) > 2 else ""
    return level, tag, value, None


def parse_gedcom_tree(path) -> list[Node]:
    """Parse the GEDCOM into a list of top-level record trees, joining
    CONC/CONT continuation lines back into the value they extend."""
    roots: list[Node] = []
    stack: dict[int, Node] = {}
    with path.open(encoding="utf-8-sig", errors="replace") as f:
        for raw_line in f:
            line = raw_line.rstrip("\r\n")
            if not line.strip():
                continue
            level, tag, value, xref = _parse_line(line)
            if not tag:
                continue
            if tag in ("CONC", "CONT"):
                target = stack.get(level - 1)
                if target is not None:
                    target.value += ("" if tag == "CONC" else "\n") + value
                continue
            node = Node(tag=tag, value=value, xref=xref)
            if level == 0:
                roots.append(node)
            else:
                parent = stack.get(level - 1)
                if parent is not None:
                    parent.children.append(node)
            stack[level] = node
            for deeper in [lvl for lvl in stack if lvl > level]:
                del stack[deeper]
    return roots


def _repository_fields(node: Node) -> dict:
    addr = node.child("ADDR")
    return {
        "name": node.child_value("NAME") or node.child_value("ABBR") or "Unnamed repository",
        "url": node.child_value("WWW") or (addr.child_value("WWW") if addr else ""),
        "notes": node.child_value("NOTE"),
    }


def _source_fields(node: Node) -> dict:
    publ = node.child("PUBL")
    publisher = node.child_value("PUBL")
    if publ is not None and not publisher:
        bits = [publ.child_value("DATE"), publ.child_value("PLAC")]
        publisher = ", ".join(b for b in bits if b)
    repo = node.child("REPO")
    return {
        "title": node.child_value("TITL") or node.child_value("ABBR") or "Untitled source",
        "author": node.child_value("AUTH"),
        "publisher": publisher,
        "apid": node.child_value("_APID"),
        "repo_xref": repo.value if (repo and repo.value.startswith("@")) else "",
        "notes": node.child_value("NOTE"),
    }


def _collect_citations(root: Node) -> list[dict]:
    """Every inline ``SOUR @S..@`` citation under one INDI/FAM record, tagged
    with the level-1 event it documents."""
    out: list[dict] = []

    def cite(node: Node, event: str) -> dict:
        data = node.child("DATA")
        text = node.child_value("TEXT") or (data.child_value("TEXT") if data else "")
        www = node.child_value("WWW") or (data.child_value("WWW") if data else "")
        return {
            "source_xref": node.value,
            "event": event,
            "page": node.child_value("PAGE"),
            "transcript": text,
            "url": www,
            "quay": node.child_value("QUAY"),
            "apid": node.child_value("_APID"),
            "note": node.child_value("NOTE"),
        }

    def walk(node: Node, event: str) -> None:
        for c in node.children:
            if c.tag == "SOUR" and c.value.startswith("@"):
                out.append(cite(c, event))
            else:
                walk(c, event)

    for c in root.children:
        if c.tag == "SOUR" and c.value.startswith("@"):
            out.append(cite(c, "individual"))
        else:
            walk(c, c.tag)
    return out


def normalize_sources(path=ORIGINAL_DIR / "Troy Tree.ged", db_path=WORKING_DB) -> dict:
    initialize_database(db_path)
    roots = parse_gedcom_tree(path)
    repos = {r.xref: r for r in roots if r.tag == "REPO"}
    sources = [r for r in roots if r.tag == "SOUR" and r.xref]
    records = [r for r in roots if r.tag in ("INDI", "FAM") and r.xref]

    stats = {"repositories": 0, "sources": 0, "citations": 0, "unmatched_sources": 0}
    with connect(db_path) as con:
        # idempotent: drop only the rows this module owns, then rebuild
        real_source_ids = [
            row[0]
            for row in con.execute(
                "SELECT source_id FROM source WHERE source_type = ?", (REAL_SOURCE_TYPE,)
            )
        ]
        if real_source_ids:
            con.executemany(
                "DELETE FROM citation WHERE source_id = ?", [(sid,) for sid in real_source_ids]
            )
            con.executemany(
                "DELETE FROM source WHERE source_id = ?", [(sid,) for sid in real_source_ids]
            )

        # raw_record xref -> raw_record_id (created by gedcom_import; needed to
        # attach citations to the person/family record they came from)
        raw_ids = {
            row["xref"]: row["raw_record_id"]
            for row in con.execute("SELECT raw_record_id, xref FROM raw_record")
        }

        # repositories
        repo_ids: dict[str, int] = {}
        for xref, node in repos.items():
            fields = _repository_fields(node)
            existing = con.execute(
                "SELECT repository_id FROM repository WHERE name = ?", (fields["name"],)
            ).fetchone()
            if existing:
                repo_ids[xref] = existing["repository_id"]
            else:
                cur = con.execute(
                    "INSERT INTO repository (name, url, notes) VALUES (?, ?, ?)",
                    (fields["name"], fields["url"], fields["notes"]),
                )
                repo_ids[xref] = cur.lastrowid
                stats["repositories"] += 1

        # sources
        source_ids: dict[str, int] = {}
        for node in sources:
            f = _source_fields(node)
            cur = con.execute(
                """
                INSERT INTO source (
                    gedcom_xref, repository_id, source_title, source_type,
                    source_quality, author, publisher, apid, notes
                ) VALUES (?, ?, ?, ?, 'derivative', ?, ?, ?, ?)
                """,
                (
                    node.xref,
                    repo_ids.get(f["repo_xref"]),
                    f["title"],
                    REAL_SOURCE_TYPE,
                    f["author"],
                    f["publisher"],
                    f["apid"],
                    f["notes"],
                ),
            )
            source_ids[node.xref] = cur.lastrowid
            stats["sources"] += 1

        # inline citations, attached to the person/family raw record
        for root in records:
            raw_record_id = raw_ids.get(root.xref)
            for c in _collect_citations(root):
                source_id = source_ids.get(c["source_xref"])
                if source_id is None:
                    stats["unmatched_sources"] += 1
                    continue
                info_type = QUAY_INFO.get(c["quay"], "unknown")
                con.execute(
                    """
                    INSERT INTO citation (
                        source_id, raw_record_id, page_locator, url, transcript,
                        abstract, citation_text, information_type, evidence_type,
                        review_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unknown', 'imported')
                    """,
                    (
                        source_id,
                        raw_record_id,
                        c["page"],
                        c["url"],
                        c["transcript"],
                        c["note"],
                        f"{root.xref} {c['event']} citation",
                        info_type,
                    ),
                )
                stats["citations"] += 1
        con.commit()
    return stats


if __name__ == "__main__":
    path = ORIGINAL_DIR / sys.argv[1] if len(sys.argv) > 1 else ORIGINAL_DIR / "Troy Tree.ged"
    result = normalize_sources(path)
    print(
        f"Normalized {result['sources']} sources, {result['repositories']} repositories, "
        f"{result['citations']} citations "
        f"({result['unmatched_sources']} citations skipped: source not found)"
    )
