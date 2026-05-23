from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from .paths import ORIGINAL_DIR, PILOT_DB, WORKING_DB

EXPECTED_FILES = [
    "Troy Tree.ged",
    "troy_tree_research_pilot.sqlite",
    "persons.csv",
    "evidence_candidates.csv",
    "research_queue.csv",
    "README.md",
]


def csv_columns(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        return next(reader, [])


def csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        return max(0, sum(1 for _ in f) - 1)


def sqlite_tables(path: Path) -> list[dict]:
    if not path.exists():
        return []
    con = sqlite3.connect(path)
    try:
        tables = []
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            if name == "sqlite_sequence":
                continue
            count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            columns = [row[1] for row in con.execute(f"PRAGMA table_info({name})")]
            tables.append({"name": name, "row_count": count, "columns": columns})
        return tables
    finally:
        con.close()


def inspect_project() -> dict:
    files = []
    for name in EXPECTED_FILES:
        path = ORIGINAL_DIR / name
        files.append(
            {
                "name": name,
                "exists": path.exists(),
                "size": path.stat().st_size if path.exists() else None,
            }
        )
    csvs = {
        name: {
            "columns": csv_columns(ORIGINAL_DIR / name),
            "row_count": csv_row_count(ORIGINAL_DIR / name),
        }
        for name in ("persons.csv", "evidence_candidates.csv", "research_queue.csv")
    }
    return {
        "files": files,
        "pilot_tables": sqlite_tables(PILOT_DB),
        "working_tables": sqlite_tables(WORKING_DB),
        "csvs": csvs,
    }


if __name__ == "__main__":
    import pprint

    pprint.pp(inspect_project())

