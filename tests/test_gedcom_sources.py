"""Tests for deep GEDCOM source normalization."""

from __future__ import annotations

from src.gedcom_sources import (
    Node,
    _collect_citations,
    normalize_sources,
    parse_gedcom_tree,
)
from src.init_database import connect, initialize_database

# A minimal GEDCOM: one repository, two real source records, and one person
# who cites both — once at the individual level and once under a BIRT event
# with a PAGE locator. The PUBL value is split across a CONC continuation line.
SAMPLE_GED = """0 HEAD
1 CHAR UTF-8
0 @R1@ REPO
1 NAME Ancestry.com
0 @S1@ SOUR
1 TITL 1850 United States Federal Census
1 AUTH Ancestry.com
1 PUBL Ancestry.com Operations,
2 CONC  Inc.
1 _APID 1,8054::0
1 REPO @R1@
0 @S2@ SOUR
1 TITL U.S., Find a Grave Index
1 AUTH Ancestry.com
0 @I9@ INDI
1 NAME John /Tester/
1 SOUR @S2@
2 _APID 1,60525::1
1 BIRT
2 DATE 1820
2 SOUR @S1@
3 PAGE Year: 1850; Census Place: Belmont, Waldo, Maine
3 QUAY 3
0 TRLR
"""


def _write_ged(tmp_path):
    ged = tmp_path / "sample.ged"
    ged.write_text(SAMPLE_GED, encoding="utf-8")
    return ged


def test_parse_tree_joins_conc_continuation(tmp_path):
    roots = parse_gedcom_tree(_write_ged(tmp_path))
    source = next(r for r in roots if r.xref == "@S1@")
    # "Ancestry.com Operations," + " Inc." with no inserted space
    assert source.child_value("PUBL") == "Ancestry.com Operations, Inc."
    assert source.child_value("TITL") == "1850 United States Federal Census"


def test_collect_citations_attributes_event_and_page():
    root = Node(tag="INDI", xref="@I9@")
    birt = Node(tag="BIRT")
    birt.children.append(Node(tag="SOUR", value="@S1@", children=[Node(tag="PAGE", value="p. 7")]))
    root.children.append(Node(tag="SOUR", value="@S2@"))  # individual-level citation
    root.children.append(birt)

    cites = _collect_citations(root)
    by_source = {c["source_xref"]: c for c in cites}
    assert by_source["@S2@"]["event"] == "individual"
    assert by_source["@S1@"]["event"] == "BIRT"
    assert by_source["@S1@"]["page"] == "p. 7"


def test_normalize_writes_sources_repos_and_citations(tmp_path):
    db = tmp_path / "t.sqlite"
    initialize_database(db)
    # gedcom_import normally creates the raw_record; seed the one we need so the
    # person's citations attach to their record.
    with connect(db) as con:
        con.execute("INSERT INTO import_batch (source_name) VALUES ('test')")
        con.execute(
            "INSERT INTO raw_record (import_batch_id, xref, record_type, raw_text) "
            "VALUES (1, '@I9@', 'INDI', '')"
        )
        con.commit()

    stats = normalize_sources(_write_ged(tmp_path), db)
    assert stats == {"repositories": 1, "sources": 2, "citations": 2, "unmatched_sources": 0}

    with connect(db) as con:
        src = con.execute(
            "SELECT * FROM source WHERE gedcom_xref = '@S1@'"
        ).fetchone()
        assert src["source_title"] == "1850 United States Federal Census"
        assert src["author"] == "Ancestry.com"
        assert src["publisher"] == "Ancestry.com Operations, Inc."
        assert src["apid"] == "1,8054::0"
        assert src["repository_id"] is not None  # linked to @R1@

        # the BIRT citation carries the PAGE locator and primary (QUAY 3) info type
        cite = con.execute(
            """
            SELECT c.page_locator, c.information_type, c.citation_text
            FROM citation c JOIN source s ON s.source_id = c.source_id
            WHERE s.gedcom_xref = '@S1@'
            """
        ).fetchone()
        assert "Belmont, Waldo, Maine" in cite["page_locator"]
        assert cite["information_type"] == "primary"
        assert cite["citation_text"] == "@I9@ BIRT citation"


def test_normalize_is_idempotent(tmp_path):
    db = tmp_path / "t.sqlite"
    initialize_database(db)
    ged = _write_ged(tmp_path)
    normalize_sources(ged, db)
    normalize_sources(ged, db)
    # the DB end-state is stable: re-running replaces, never duplicates
    with connect(db) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM source WHERE source_type = 'GEDCOM source record'"
        ).fetchone()[0] == 2
        assert con.execute("SELECT COUNT(*) FROM repository").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM citation").fetchone()[0] == 2
