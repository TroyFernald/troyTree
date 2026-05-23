from __future__ import annotations

VARIANTS = {
    "Meservie": ["Meserve", "Meservey"],
    "Meserve": ["Meservie", "Meservey"],
    "McKay": ["Mackay", "MacKay"],
    "Mackay": ["McKay", "MacKay"],
}

TARGET_SOURCES = [
    "FamilySearch",
    "WikiTree",
    "Find a Grave",
    "Internet Archive",
    "Google Books",
    "Maine town histories",
    "county histories",
    "US census indexes",
    "newspaper obituary indexes",
]


def build_search_terms(person: dict) -> list[str]:
    name = person.get("full_name") or person.get("name") or ""
    birth_date = person.get("birth_date", "")
    death_date = person.get("death_date", "")
    birth_year = birth_date[-4:] if birth_date[-4:].isdigit() else birth_date[:4]
    death_year = death_date[-4:] if death_date[-4:].isdigit() else death_date[:4]
    birth_place = (person.get("birth_place") or "").split(",")[0]
    surname = person.get("surname") or (name.split()[-1] if name.split() else "")
    spouse_names = person.get("spouse_names") or "spouse name"

    searches = [
        f'"{name}" "{birth_year}" "{death_year}" genealogy',
        f'"{name}" "{spouse_names}"',
        f'"{name}" "{birth_place}"',
        f'"{name}" parents',
        f'"{name}" "Find a Grave"',
        f'"{name}" "FamilySearch"',
        f'"{name}" "WikiTree"',
        f'"{name}" Maine',
        f'"{name}" "New Hampshire"',
        f'"{name}" "Nova Scotia"',
    ]
    for variant in VARIANTS.get(surname, []):
        searches.append(f'"{name.replace(surname, variant)}" genealogy')
    return [s for s in searches if '""' not in s]

