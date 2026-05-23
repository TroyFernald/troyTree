from __future__ import annotations

import sqlite3

import pandas as pd

from .date_validation import find_date_issues
from .inspect_database import inspect_project
from .paths import EXPORTS_DIR, WORKING_DB, ensure_directories
from .research_queue import build_search_terms


def read_sql(con: sqlite3.Connection, query: str) -> pd.DataFrame:
    return pd.read_sql_query(query, con)


def write_setup_report(summary: dict) -> None:
    lines = [
        "# Project Setup Report",
        "",
        "## Files Found",
        "",
        "| File | Found | Size |",
        "| --- | --- | ---: |",
    ]
    for item in summary["files"]:
        size = item["size"] if item["size"] is not None else ""
        lines.append(f"| {item['name']} | {item['exists']} | {size} |")

    missing = [item["name"] for item in summary["files"] if not item["exists"]]
    lines.extend(["", "## Missing Expected Files", ""])
    lines.append(", ".join(missing) if missing else "None.")

    lines.extend(["", "## Pilot SQLite Tables", ""])
    if summary["pilot_tables"]:
        for table in summary["pilot_tables"]:
            lines.append(f"- `{table['name']}`: {table['row_count']} rows")
            lines.append(f"  - Columns: {', '.join(table['columns'])}")
    else:
        lines.append("No pilot SQLite tables found.")

    lines.extend(["", "## Working SQLite Tables", ""])
    if summary["working_tables"]:
        for table in summary["working_tables"]:
            lines.append(f"- `{table['name']}`: {table['row_count']} rows")
            lines.append(f"  - Columns: {', '.join(table['columns'])}")
    else:
        lines.append("Working database has not been created yet.")

    lines.extend(["", "## CSV Columns", ""])
    for name, info in summary["csvs"].items():
        lines.append(f"- `{name}`: {info['row_count']} rows")
        lines.append(f"  - Columns: {', '.join(info['columns'])}")

    lines.extend(
        [
            "",
            "## Recommended Next Steps",
            "",
            "1. Review all `needs_review` evidence before changing any master tree data.",
            "2. Resolve the Daniel Smith Meservie death-date conflict against an original record or cemetery source.",
            "3. Prioritize direct ancestors with zero sources or only `Ancestry Family Trees` source coverage.",
            "4. Add original record searches for Maine, New Hampshire, Massachusetts, and Nova Scotia ancestors in generations 4 through 8.",
            "5. Keep `data/original/` read-only and run all SQLite work from `data/working/research.sqlite`.",
        ]
    )
    (EXPORTS_DIR / "project_setup_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_workbook_sheets(con: sqlite3.Connection, writer: pd.ExcelWriter) -> None:
    queue = read_sql(con, "SELECT * FROM research_queue ORDER BY priority, person_name")
    people = read_sql(con, "SELECT * FROM people ORDER BY generation, full_name")
    evidence = read_sql(con, "SELECT * FROM evidence_candidates ORDER BY confidence_score DESC")
    duplicates = read_sql(con, "SELECT * FROM duplicate_candidates ORDER BY score DESC")

    queue.head(25).to_excel(writer, sheet_name="Top Priority People", index=False)
    people[
        people["confidence_status"].isin(["unsourced", "weak_source_only"])
    ].to_excel(writer, sheet_name="Weakly Sourced Direct Ancestors", index=False)

    date_conflict_rows = []
    for _, person in people.iterrows():
        for issue in find_date_issues(person["birth_date"], person["death_date"], person_name=person["full_name"]):
            date_conflict_rows.append(
                {
                    "person_id": person["person_id"],
                    "person_name": person["full_name"],
                    "field": issue.field,
                    "issue": issue.message,
                }
            )
    evidence_conflicts = evidence[evidence["conflicts"].fillna("") != ""]
    for _, row in evidence_conflicts.iterrows():
        date_conflict_rows.append(
            {
                "person_id": row["person_id"],
                "person_name": row["person_name"],
                "field": "evidence",
                "issue": row["summary"],
            }
        )
    pd.DataFrame(date_conflict_rows).to_excel(writer, sheet_name="Date Conflicts", index=False)
    duplicates.to_excel(writer, sheet_name="Duplicate Candidates", index=False)

    suggested = []
    for _, person in people.iterrows():
        for term in build_search_terms(person.to_dict()):
            suggested.append(
                {
                    "person_id": person["person_id"],
                    "person_name": person["full_name"],
                    "search": term,
                }
            )
    pd.DataFrame(suggested).to_excel(writer, sheet_name="Suggested Searches", index=False)


def export_reports() -> None:
    ensure_directories()
    with sqlite3.connect(WORKING_DB) as con:
        con.row_factory = sqlite3.Row
        read_sql(con, "SELECT * FROM research_queue ORDER BY priority, person_name").to_csv(
            EXPORTS_DIR / "research_queue_export.csv", index=False
        )
        read_sql(
            con,
            """
            SELECT evidence_id, person_id, person_name, source_title, source_type, source_url,
                   source_site, summary, confidence_score, confidence_label, conflicts,
                   review_status, review_notes
            FROM evidence_candidates
            ORDER BY confidence_score DESC, person_name
            """,
        ).to_csv(EXPORTS_DIR / "evidence_candidates_export.csv", index=False)
        read_sql(con, "SELECT * FROM proposed_updates ORDER BY person_name, field_name").to_csv(
            EXPORTS_DIR / "proposed_updates.csv", index=False
        )
        read_sql(con, "SELECT * FROM people ORDER BY generation, full_name").to_excel(
            EXPORTS_DIR / "direct_ancestor_audit.xlsx", index=False
        )
        with pd.ExcelWriter(EXPORTS_DIR / "next_research_targets.xlsx", engine="openpyxl") as writer:
            add_workbook_sheets(con, writer)

    write_setup_report(inspect_project())


if __name__ == "__main__":
    export_reports()
    print(f"Reports written to {EXPORTS_DIR}")

