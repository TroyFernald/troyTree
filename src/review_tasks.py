from __future__ import annotations

import sqlite3

from .paths import WORKING_DB


def rebuild_review_tasks(db_path=WORKING_DB) -> int:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        con.execute(
            "DELETE FROM review_task WHERE task_type IN ('citation_gap', 'proof_gap', 'duplicate_review', 'validation_issue')"
        )

        direct_rows = con.execute(
            """
            SELECT *
            FROM direct_ancestor_audit
            WHERE generation > 0
            """
        ).fetchall()
        for row in direct_rows:
            flags = row["audit_flags"] or ""
            if "no sources" in flags or "weak source only" in flags:
                con.execute(
                    """
                    INSERT INTO review_task (
                        task_type, subject_type, subject_id, person_id, person_name,
                        priority, reason, status
                    ) VALUES ('citation_gap', 'person', ?, ?, ?, ?, ?, 'open')
                    """,
                    (
                        row["person_id"],
                        row["person_id"],
                        row["person_name"],
                        row["priority"],
                        flags,
                    ),
                )
            if "date" in flags.lower() or "missing birth" in flags.lower():
                con.execute(
                    """
                    INSERT INTO review_task (
                        task_type, subject_type, subject_id, person_id, person_name,
                        priority, reason, status
                    ) VALUES ('proof_gap', 'person', ?, ?, ?, ?, ?, 'open')
                    """,
                    (
                        row["person_id"],
                        row["person_id"],
                        row["person_name"],
                        row["priority"],
                        flags,
                    ),
                )

        for row in con.execute(
            """
            SELECT *
            FROM duplicate_candidates
            WHERE score >= 95
            ORDER BY score DESC
            LIMIT 100
            """
        ):
            con.execute(
                """
                INSERT INTO review_task (
                    task_type, subject_type, subject_id, person_id, person_name,
                    priority, reason, status
                ) VALUES ('duplicate_review', 'duplicate_candidate', ?, ?, ?, ?, ?, 'open')
                """,
                (
                    str(row["duplicate_id"]),
                    row["left_person_id"],
                    row["left_name"],
                    max(1, 100 - int(row["score"] or 0)),
                    f"{row['left_name']} <> {row['right_name']}: {row['reason']}",
                ),
            )
        for row in con.execute(
            """
            SELECT *
            FROM validation_issue
            WHERE review_status = 'open'
            ORDER BY
              CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
              END,
              generation,
              person_name
            LIMIT 200
            """
        ):
            priority = {"critical": 1, "high": 5, "medium": 20}.get(row["severity"], 50)
            con.execute(
                """
                INSERT INTO review_task (
                    task_type, subject_type, subject_id, person_id, person_name,
                    priority, reason, status
                ) VALUES ('validation_issue', 'validation_issue', ?, ?, ?, ?, ?, 'open')
                """,
                (
                    str(row["validation_issue_id"]),
                    row["person_id"],
                    row["person_name"],
                    priority,
                    f"{row['severity']}: {row['issue_type']} - {row['description']}",
                ),
            )
        con.commit()
        return con.execute("SELECT COUNT(*) FROM review_task WHERE status = 'open'").fetchone()[0]
    finally:
        con.close()


if __name__ == "__main__":
    print(f"Open review tasks: {rebuild_review_tasks()}")
