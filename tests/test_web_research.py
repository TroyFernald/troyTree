from src.web_research import load_seed_findings, suggested_public_searches


def test_seed_findings_load():
    findings = load_seed_findings()
    assert any(finding["person_name"] == "Daniel Smith Sr. Meservie" for finding in findings)


def test_suggested_public_searches_include_public_sites():
    searches = suggested_public_searches(
        {
            "full_name": "Daniel Smith Meservie",
            "birth_date": "1842",
            "death_date": "1923",
            "birth_place": "Belmont, Waldo, Maine",
            "surname": "Meservie",
        }
    )
    assert any("FamilySearch" in search for search in searches)
    assert any("Find a Grave" in search for search in searches)
    assert any("Meservey" in search for search in searches)

