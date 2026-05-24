from __future__ import annotations

import sqlite3

from .paths import WORKING_DB, ensure_directories


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS import_batch (
    import_batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_path TEXT,
    source_hash TEXT,
    source_type TEXT,
    gedcom_version TEXT,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    parser_version TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS raw_record (
    raw_record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER NOT NULL,
    xref TEXT,
    record_type TEXT,
    raw_text TEXT NOT NULL,
    parsed_summary TEXT,
    FOREIGN KEY(import_batch_id) REFERENCES import_batch(import_batch_id)
);

CREATE TABLE IF NOT EXISTS repository (
    repository_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS source (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER,
    source_title TEXT NOT NULL,
    source_type TEXT,
    source_url TEXT,
    source_quality TEXT DEFAULT 'unknown',
    notes TEXT,
    FOREIGN KEY(repository_id) REFERENCES repository(repository_id)
);

CREATE TABLE IF NOT EXISTS citation (
    citation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER,
    raw_record_id INTEGER,
    page_locator TEXT,
    url TEXT,
    accessed_date TEXT,
    transcript TEXT,
    abstract TEXT,
    citation_text TEXT,
    information_type TEXT DEFAULT 'unknown',
    evidence_type TEXT DEFAULT 'unknown',
    review_status TEXT DEFAULT 'imported',
    FOREIGN KEY(source_id) REFERENCES source(source_id),
    FOREIGN KEY(raw_record_id) REFERENCES raw_record(raw_record_id)
);

CREATE TABLE IF NOT EXISTS evidence_assertion (
    assertion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_batch_id INTEGER,
    raw_record_id INTEGER,
    citation_id INTEGER,
    subject_type TEXT NOT NULL,
    subject_id TEXT,
    person_id TEXT,
    claim_type TEXT NOT NULL,
    claim_value TEXT,
    date_text TEXT,
    place_text TEXT,
    source_quality TEXT DEFAULT 'unknown',
    information_type TEXT DEFAULT 'unknown',
    evidence_type TEXT DEFAULT 'unknown',
    confidence_score INTEGER DEFAULT 0,
    confidence_label TEXT DEFAULT 'Weak clue only',
    review_status TEXT DEFAULT 'imported',
    review_notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(import_batch_id) REFERENCES import_batch(import_batch_id),
    FOREIGN KEY(raw_record_id) REFERENCES raw_record(raw_record_id),
    FOREIGN KEY(citation_id) REFERENCES citation(citation_id),
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS people (
    person_id TEXT PRIMARY KEY,
    gedcom_id TEXT,
    full_name TEXT NOT NULL,
    given_name TEXT,
    surname TEXT,
    birth_date TEXT,
    birth_place TEXT,
    death_date TEXT,
    death_place TEXT,
    spouse_names TEXT,
    parent_names TEXT,
    generation INTEGER,
    relationship_to_root TEXT,
    source_count INTEGER DEFAULT 0,
    confidence_status TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS evidence_candidates (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT,
    person_name TEXT,
    source_title TEXT,
    source_type TEXT,
    source_url TEXT,
    source_site TEXT,
    claimed_birth_date TEXT,
    claimed_birth_place TEXT,
    claimed_death_date TEXT,
    claimed_death_place TEXT,
    claimed_spouse TEXT,
    claimed_parents TEXT,
    claimed_children TEXT,
    summary TEXT,
    transcription TEXT,
    confidence_score INTEGER,
    confidence_label TEXT,
    conflicts TEXT,
    date_found TEXT,
    review_status TEXT DEFAULT 'needs_review',
    review_notes TEXT,
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS web_research_finding (
    finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT,
    person_name TEXT,
    search_query TEXT,
    source_title TEXT,
    source_type TEXT,
    source_url TEXT,
    source_site TEXT,
    snippet TEXT,
    claimed_facts TEXT,
    confidence_score INTEGER,
    confidence_label TEXT,
    review_status TEXT DEFAULT 'needs_review',
    date_found TEXT DEFAULT CURRENT_DATE,
    notes TEXT,
    UNIQUE(person_id, source_url),
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS web_research_target (
    target_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT,
    person_name TEXT,
    generation INTEGER,
    priority INTEGER,
    reason TEXT,
    search_query TEXT,
    target_sources TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(person_id, search_query),
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS research_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT,
    person_name TEXT,
    priority INTEGER,
    reason TEXT,
    search_terms TEXT,
    target_sources TEXT,
    status TEXT DEFAULT 'open',
    assigned_to TEXT,
    created_date TEXT,
    last_researched_date TEXT,
    notes TEXT,
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS proposed_updates (
    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT,
    person_name TEXT,
    field_name TEXT,
    current_value TEXT,
    proposed_value TEXT,
    reason TEXT,
    supporting_evidence_ids TEXT,
    confidence_score INTEGER,
    review_status TEXT DEFAULT 'not_reviewed',
    review_notes TEXT,
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS conclusion_evidence (
    conclusion_evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    conclusion_table TEXT NOT NULL,
    conclusion_id TEXT NOT NULL,
    assertion_id INTEGER NOT NULL,
    support_type TEXT DEFAULT 'supports',
    notes TEXT,
    FOREIGN KEY(assertion_id) REFERENCES evidence_assertion(assertion_id)
);

CREATE TABLE IF NOT EXISTS review_task (
    review_task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT,
    person_id TEXT,
    person_name TEXT,
    priority INTEGER DEFAULT 999,
    reason TEXT,
    status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,
    reviewed_by TEXT,
    review_notes TEXT,
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS validation_issue (
    validation_issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    person_id TEXT,
    person_name TEXT,
    related_person_id TEXT,
    related_person_name TEXT,
    relationship_id INTEGER,
    generation INTEGER,
    description TEXT NOT NULL,
    review_status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(person_id) REFERENCES people(person_id),
    FOREIGN KEY(related_person_id) REFERENCES people(person_id),
    FOREIGN KEY(relationship_id) REFERENCES family_relationships(relationship_id)
);

CREATE TABLE IF NOT EXISTS notable_person_candidate (
    notable_candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT,
    person_name TEXT,
    generation INTEGER,
    relationship_to_root TEXT,
    birth_date TEXT,
    death_date TEXT,
    birth_place TEXT,
    death_place TEXT,
    category TEXT,
    notable_reason TEXT,
    risk_level TEXT,
    proof_status TEXT DEFAULT 'unverified',
    review_notes TEXT,
    UNIQUE(person_id, category, notable_reason),
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS change_log (
    change_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    change_type TEXT NOT NULL,
    table_name TEXT,
    row_id TEXT,
    person_id TEXT,
    summary TEXT,
    changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    changed_by TEXT,
    review_task_id INTEGER,
    FOREIGN KEY(person_id) REFERENCES people(person_id),
    FOREIGN KEY(review_task_id) REFERENCES review_task(review_task_id)
);

CREATE TABLE IF NOT EXISTS family_relationships (
    relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id TEXT,
    person_id TEXT,
    related_person_id TEXT,
    relationship_type TEXT,
    notes TEXT,
    FOREIGN KEY(person_id) REFERENCES people(person_id),
    FOREIGN KEY(related_person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS direct_ancestor_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT,
    person_name TEXT,
    generation INTEGER,
    birth_date TEXT,
    birth_place TEXT,
    death_date TEXT,
    death_place TEXT,
    spouse_names TEXT,
    parent_names TEXT,
    source_count INTEGER,
    confidence_status TEXT,
    audit_flags TEXT,
    priority INTEGER,
    notes TEXT,
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);

CREATE TABLE IF NOT EXISTS duplicate_candidates (
    duplicate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    left_person_id TEXT,
    right_person_id TEXT,
    left_name TEXT,
    right_name TEXT,
    left_birth_date TEXT,
    right_birth_date TEXT,
    left_birth_place TEXT,
    right_birth_place TEXT,
    left_death_date TEXT,
    right_death_date TEXT,
    left_death_place TEXT,
    right_death_place TEXT,
    left_relationship_to_root TEXT,
    right_relationship_to_root TEXT,
    score INTEGER,
    reason TEXT,
    review_status TEXT DEFAULT 'needs_review'
);
"""


def connect(db_path=WORKING_DB) -> sqlite3.Connection:
    ensure_directories()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def initialize_database(db_path=WORKING_DB) -> None:
    with connect(db_path) as con:
        con.executescript(SCHEMA)
        ensure_duplicate_columns(con)
        ensure_review_columns(con)


def ensure_duplicate_columns(con: sqlite3.Connection) -> None:
    existing = {row["name"] for row in con.execute("PRAGMA table_info(duplicate_candidates)")}
    columns = {
        "left_birth_date": "TEXT",
        "right_birth_date": "TEXT",
        "left_birth_place": "TEXT",
        "right_birth_place": "TEXT",
        "left_death_date": "TEXT",
        "right_death_date": "TEXT",
        "left_death_place": "TEXT",
        "right_death_place": "TEXT",
        "left_relationship_to_root": "TEXT",
        "right_relationship_to_root": "TEXT",
    }
    for column, column_type in columns.items():
        if column not in existing:
            con.execute(f"ALTER TABLE duplicate_candidates ADD COLUMN {column} {column_type}")


def ensure_review_columns(con: sqlite3.Connection) -> None:
    review_existing = {row["name"] for row in con.execute("PRAGMA table_info(review_task)")}
    review_columns = {
        "reviewed_at": "TEXT",
        "reviewed_by": "TEXT",
        "review_notes": "TEXT",
    }
    for column, column_type in review_columns.items():
        if column not in review_existing:
            con.execute(f"ALTER TABLE review_task ADD COLUMN {column} {column_type}")


if __name__ == "__main__":
    initialize_database()
    print(f"Initialized {WORKING_DB}")
