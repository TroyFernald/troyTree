"""Tests for the prioritized research batch runner."""

from __future__ import annotations

from src.init_database import connect, initialize_database
from src.research_batch import build_worklist, status


def _seed(db):
    initialize_database(db)
    with connect(db) as con:
        people = [
            # id, name, surname, gen, b_date, b_place, d_date, d_place, conf, src_count
            ("p_weak6", "Weak Six", "Fernald", 6, "1780", "Belmont, Waldo, Maine", "1840", "Maine", "unsourced", 0),
            ("p_weak8", "Weak Eight", "Fuller", 8, "1700", "Newton, Massachusetts", "1764", "Massachusetts", "weak_source_only", 1),
            ("p_strong5", "Strong Five", "Adams", 5, "1800", "Maine", "1870", "Maine", "needs_review", 6),
            ("p_far14", "Far Fourteen", "Capet", 14, "1300", "France", "1360", "France", "unsourced", 0),
            ("p_living", "Living Person", "Fernald", 1, "1990", "Maine", "", "", "needs_review", 2),
        ]
        con.executemany(
            "INSERT INTO people (person_id, full_name, surname, generation, birth_date, "
            "birth_place, death_date, death_place, confidence_status, source_count) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            people,
        )
        # priority: lower = more important. Weak gen-6/8 beat strong gen-5; far gen-14 worst.
        targets = [
            ("p_weak6", 6, 25),
            ("p_weak8", 8, 30),
            ("p_strong5", 5, 50),
            ("p_far14", 14, 140),
            ("p_living", 1, 5),
        ]
        for pid, gen, pri in targets:
            con.execute(
                "INSERT INTO web_research_target (person_id, person_name, generation, priority, "
                "search_query, status) VALUES (?, ?, ?, ?, ?, 'open')",
                (pid, pid, gen, pri, f"{pid} query"),
            )
        con.commit()


def test_worklist_orders_by_priority_and_excludes_living(tmp_path):
    db = tmp_path / "t.sqlite"
    _seed(db)
    work = build_worklist(limit=10, db_path=db)
    ids = [p["person_id"] for p in work]
    # living person excluded despite the best (lowest) priority number
    assert "p_living" not in ids
    # remaining ordered by priority ascending
    assert ids == ["p_weak6", "p_weak8", "p_strong5", "p_far14"]
    # each person carries suggested searches and target sources for the agent
    assert work[0]["suggested_searches"]
    assert work[0]["target_sources"]


def test_worklist_generation_filter(tmp_path):
    db = tmp_path / "t.sqlite"
    _seed(db)
    work = build_worklist(limit=10, gen_min=4, gen_max=8, db_path=db)
    gens = {p["generation"] for p in work}
    assert gens <= {5, 6, 8}
    assert "p_far14" not in {p["person_id"] for p in work}


def test_worklist_weak_only_filter(tmp_path):
    db = tmp_path / "t.sqlite"
    _seed(db)
    work = build_worklist(limit=10, weak_only=True, db_path=db)
    ids = {p["person_id"] for p in work}
    assert "p_strong5" not in ids  # well-sourced, excluded
    assert {"p_weak6", "p_weak8"} <= ids


def test_status_counts_open_targets(tmp_path):
    db = tmp_path / "t.sqlite"
    _seed(db)
    s = status(db)
    assert s["open_targets"] == 5
    assert s["people_remaining"] == 5
