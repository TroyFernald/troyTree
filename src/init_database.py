from __future__ import annotations

import sqlite3

from .paths import WORKING_DB, ensure_directories


SCHEMA = """
PRAGMA foreign_keys = ON;

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

CREATE TABLE IF NOT EXISTS duplicate_candidates (
    duplicate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    left_person_id TEXT,
    right_person_id TEXT,
    left_name TEXT,
    right_name TEXT,
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


if __name__ == "__main__":
    initialize_database()
    print(f"Initialized {WORKING_DB}")
