"""Tag each direct ancestor with which side of the family they belong to.

The root person's two parents define the two sides: parent slot 0 (paternal) and
slot 1 (maternal). Here that is the **Fernald** side (Stephen A Fernald) and the
**Bagley** side (Judith E Bagley), but the labels are derived from the data, not
hard-coded, so this keeps working if the tree's root changes.

``compute_sides`` walks parent links upward from each gen-1 ancestor and tags
everyone reachable. A person reachable from both sides (shared ancestor via
pedigree overlap) gets both tags; the root gets both. People who are not direct
ancestors get no tag (absent from the map).

Returns ``(sides, labels, keys)``:
  sides  -> {person_id: ["fernald"] | ["bagley"] | ["fernald","bagley"]}
  labels -> {"fernald": "Fernald", "bagley": "Bagley"}   (display names)
  keys   -> ["fernald", "bagley"]                          (paternal first)
"""

from __future__ import annotations

import sqlite3


def _parents_of(con: sqlite3.Connection, pid: str) -> list[str]:
    rows = con.execute(
        "SELECT person_id FROM family_relationships "
        "WHERE related_person_id = ? AND relationship_type = 'parent' ORDER BY person_id",
        (pid,),
    ).fetchall()
    return [r[0] for r in rows][:2]


def _key_for(surname: str, idx: int) -> str:
    base = (surname or "").strip().lower()
    return base or ("paternal" if idx == 0 else "maternal")


def compute_sides(con: sqlite3.Connection) -> tuple[dict[str, list[str]], dict[str, str], list[str]]:
    root = con.execute("SELECT person_id FROM people WHERE generation = 0").fetchone()
    if root is None:
        return {}, {}, []
    root_id = root[0]
    surname = {r[0]: (r[1] or "") for r in con.execute("SELECT person_id, surname FROM people")}

    g1 = _parents_of(con, root_id)
    sides: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    keys: list[str] = []

    for idx, anc in enumerate(g1):
        key = _key_for(surname.get(anc, ""), idx)
        labels[key] = (surname.get(anc) or "").strip() or ("Paternal" if idx == 0 else "Maternal")
        keys.append(key)
        stack, seen = [anc], set()
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            sides.setdefault(p, set()).add(key)
            stack.extend(_parents_of(con, p))

    sides[root_id] = set(keys)  # the root descends from both sides
    ordered = {pid: [k for k in keys if k in s] for pid, s in sides.items()}
    return ordered, labels, keys
