"""Catalog the local Ancestry media (synced via RootsMagic) and link each file to
people in the research database, using the RootsMagic ``.rmtree`` SQLite file as
the authoritative link source.

Why the .rmtree and not filenames or the GEDCOM: RootsMagic stores the real
media<->owner graph. A portrait links straight to a person; a record scan links
to a citation, which links to an event, which belongs to a person. We resolve
all of those hops:

    media file  ->  MultimediaTable.MediaFile -> MediaID
    MediaID     ->  MediaLinkTable
                      OwnerType 0  -> PersonID                      (portraits)
                      OwnerType 2  -> EventID  -> person            (event media)
                      OwnerType 4  -> CitationID -> CitationLink:
                                         OwnerType 0 -> PersonID
                                         OwnerType 2 -> EventID -> person  (record scans)

RootsMagic PersonIDs are mapped back to our person_id by primary name
(Given+Surname) plus birth-year tiebreak, since both trees are the same Ancestry
export. A media file can belong to several people (e.g. a census page), so links
live in a media_person_link table.

    python -m src.media_import "C:\\Tree\\ancestory-import_media" "C:\\Tree\\ancestory-import.rmtree"
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections import defaultdict

from .init_database import connect, initialize_database
from .paths import WORKING_DB

RMTREE = r"C:\Tree\ancestory-import.rmtree"
RECORD_ID_RE = re.compile(r"^[\d _\-\[\]\.]+$")
DOC_KEYWORDS = re.compile(
    r"census|certificate|obitu|marria|death|birth|\brecord\b|draft|register|\bwill\b|"
    r"deed|baptism|burial|headstone|gravestone|map of|passenger|directory|probate|"
    r"enlist|muster|pension|18\d{2}|19\d{2}", re.I)

SCHEMA = """
DROP TABLE IF EXISTS media_person_link;
DROP TABLE IF EXISTS media_object;
CREATE TABLE media_object (
    media_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_path TEXT,
    file_ext TEXT,
    file_size INTEGER,
    md5 TEXT UNIQUE,
    caption TEXT,
    media_date TEXT,
    kind TEXT,                 -- photo | document
    owner_count INTEGER DEFAULT 0,
    ocr_text TEXT,
    ocr_status TEXT DEFAULT 'pending'
);
CREATE TABLE media_person_link (
    link_id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER,
    person_id TEXT,
    person_name TEXT,
    link_type TEXT,            -- person | event | citation
    FOREIGN KEY(media_id) REFERENCES media_object(media_id),
    FOREIGN KEY(person_id) REFERENCES people(person_id)
);
CREATE INDEX idx_mpl_media ON media_person_link(media_id);
CREATE INDEX idx_mpl_person ON media_person_link(person_id);
CREATE INDEX idx_media_kind ON media_object(kind);
"""


def _rm_connect(path):
    import sqlite3
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    # RootsMagic columns use a custom collation; a case-insensitive comparison is fine.
    con.create_collation("RMNOCASE", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return con


def _year(s: str) -> str | None:
    m = re.search(r"(1[5-9]\d{2}|20\d{2})", s or "")
    return m.group(1) if m else None


def build_rm_to_ours(rm, con) -> dict:
    """Map RootsMagic PersonID -> our person_id via primary name + birth year."""
    # our side: name -> [(person_id, year)]
    ours = defaultdict(list)
    for r in con.execute("SELECT person_id, full_name, birth_date FROM people"):
        ours[(r["full_name"] or "").strip().lower()].append((r["person_id"], _year(r["birth_date"])))
    # rm birth years (EventType 1 = birth, OwnerType 0 = person)
    rm_birth = {}
    for r in rm.execute("SELECT OwnerID, Date FROM EventTable WHERE OwnerType=0 AND EventType=1"):
        rm_birth.setdefault(r["OwnerID"], _year(r["Date"]))
    mapping, ambiguous = {}, 0
    for r in rm.execute("SELECT OwnerID, Given, Surname FROM NameTable WHERE IsPrimary=1"):
        name = f"{(r['Given'] or '').strip()} {(r['Surname'] or '').strip()}".strip().lower()
        cands = ours.get(name)
        if not cands:
            continue
        if len(cands) == 1:
            mapping[r["OwnerID"]] = cands[0][0]
        else:
            by = rm_birth.get(r["OwnerID"])
            hit = [pid for pid, y in cands if y and y == by]
            mapping[r["OwnerID"]] = hit[0] if hit else cands[0][0]
            if not hit:
                ambiguous += 1
    mapping["_ambiguous"] = ambiguous
    return mapping


def build_media_to_persons(rm, rm2ours) -> dict:
    """Return {MediaID: {(our_person_id, link_type)}}."""
    # event -> person
    event_person = {r["EventID"]: r["OwnerID"]
                    for r in rm.execute("SELECT EventID, OwnerID FROM EventTable WHERE OwnerType=0")}
    # citation -> set of rm person ids (direct + via event)
    cit_persons = defaultdict(set)
    for r in rm.execute("SELECT CitationID, OwnerType, OwnerID FROM CitationLinkTable"):
        if r["OwnerType"] == 0:
            cit_persons[r["CitationID"]].add(r["OwnerID"])
        elif r["OwnerType"] == 2 and r["OwnerID"] in event_person:
            cit_persons[r["CitationID"]].add(event_person[r["OwnerID"]])

    out = defaultdict(set)
    for r in rm.execute("SELECT MediaID, OwnerType, OwnerID FROM MediaLinkTable"):
        mid, ot, oid = r["MediaID"], r["OwnerType"], r["OwnerID"]
        rm_pids, ltype = set(), None
        if ot == 0:
            rm_pids, ltype = {oid}, "person"
        elif ot == 2 and oid in event_person:
            rm_pids, ltype = {event_person[oid]}, "event"
        elif ot == 4:
            rm_pids, ltype = cit_persons.get(oid, set()), "citation"
        for rp in rm_pids:
            ours = rm2ours.get(rp)
            if ours:
                out[mid].add((ours, ltype))
    return out


def classify(name: str, ext: str, link_types: set) -> str:
    if ext in (".pdf", ".docx", ".rtf", ".htm", ".html"):
        return "document"
    if "citation" in link_types or "event" in link_types:
        return "document"
    stem = os.path.splitext(name)[0]
    if RECORD_ID_RE.match(stem.strip()) or DOC_KEYWORDS.search(stem):
        return "document"
    return "photo"


def md5_of(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_media(media_dir: str, rmtree=RMTREE, db_path=WORKING_DB) -> dict:
    initialize_database(db_path)
    rm = _rm_connect(rmtree)
    # MediaFile -> (MediaID, Caption, Date)
    media_meta = {r["MediaFile"]: (r["MediaID"], r["Caption"], r["Date"])
                  for r in rm.execute("SELECT MediaID, MediaFile, Caption, Date FROM MultimediaTable")}

    with connect(db_path) as con:
        con.executescript(SCHEMA)
        rm2ours = build_rm_to_ours(rm, con)
        amb = rm2ours.pop("_ambiguous", 0)
        media_persons = build_media_to_persons(rm, rm2ours)
        name_of = {r["person_id"]: r["full_name"] for r in con.execute("SELECT person_id, full_name FROM people")}

        stats = {"files": 0, "inserted": 0, "dupes": 0, "documents": 0, "photos": 0,
                 "links": 0, "files_with_person": 0, "files_no_person": 0,
                 "rm_people_mapped": len(rm2ours), "ambiguous_name_matches": amb}

        for fn in sorted(os.listdir(media_dir)):
            path = os.path.join(media_dir, fn)
            if not os.path.isfile(path):
                continue
            stats["files"] += 1
            mid, caption, mdate = media_meta.get(fn, (None, None, None))
            owners = media_persons.get(mid, set()) if mid else set()
            link_types = {lt for _, lt in owners}
            ext = os.path.splitext(fn)[1].lower()
            kind = classify(fn, ext, link_types)
            digest = md5_of(path)
            try:
                cur = con.execute(
                    """INSERT INTO media_object
                       (file_name,file_path,file_ext,file_size,md5,caption,media_date,kind,owner_count,ocr_status)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (fn, path, ext, os.path.getsize(path), digest, caption, mdate, kind,
                     len(owners), "pending" if kind == "document" else "n/a"))
                media_id = cur.lastrowid
                stats["inserted"] += 1
                stats["documents"] += kind == "document"
                stats["photos"] += kind == "photo"
                stats["files_with_person"] += bool(owners)
                stats["files_no_person"] += not owners
                for pid, ltype in owners:
                    con.execute(
                        "INSERT INTO media_person_link (media_id,person_id,person_name,link_type) VALUES (?,?,?,?)",
                        (media_id, pid, name_of.get(pid), ltype))
                    stats["links"] += 1
            except Exception:
                stats["dupes"] += 1
        con.commit()
    return stats


if __name__ == "__main__":
    media_dir = sys.argv[1] if len(sys.argv) > 1 else r"C:\Tree\ancestory-import_media"
    rmtree = sys.argv[2] if len(sys.argv) > 2 else RMTREE
    print(ingest_media(media_dir, rmtree))
