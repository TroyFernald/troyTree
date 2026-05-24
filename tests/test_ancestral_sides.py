import sqlite3

from src.ancestral_sides import compute_sides


def _tree() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        "CREATE TABLE people(person_id TEXT, full_name TEXT, surname TEXT, generation INTEGER);"
        "CREATE TABLE family_relationships(person_id TEXT, related_person_id TEXT, relationship_type TEXT);"
    )
    # root, paternal parent (p1, sorts first), maternal parent (p2), and one parent each above
    con.executemany("INSERT INTO people VALUES(?,?,?,?)", [
        ("root", "Root Person", "Fernald", 0),
        ("p1", "Father", "Fernald", 1),
        ("p2", "Mother", "Bagley", 1),
        ("p1a", "Grandfather", "Fernald", 2),
        ("p2a", "Grandmother", "Bagley", 2),
    ])
    con.executemany("INSERT INTO family_relationships VALUES(?,?,?)", [
        ("p1", "root", "parent"), ("p2", "root", "parent"),
        ("p1a", "p1", "parent"), ("p2a", "p2", "parent"),
    ])
    return con


def test_sides_split_by_root_parents():
    sides, labels, keys = compute_sides(_tree())
    assert keys == ["fernald", "bagley"]
    assert labels == {"fernald": "Fernald", "bagley": "Bagley"}
    assert sides["p1"] == ["fernald"]
    assert sides["p1a"] == ["fernald"]
    assert sides["p2"] == ["bagley"]
    assert sides["p2a"] == ["bagley"]
    assert set(sides["root"]) == {"fernald", "bagley"}
