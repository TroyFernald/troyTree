from src.duplicate_detection import find_duplicate_candidates


def test_duplicate_detection_finds_similar_person():
    people = [
        {"person_id": "1", "full_name": "Daniel Smith Meservie", "birth_date": "1842", "birth_place": "Maine"},
        {"person_id": "2", "full_name": "Daniel S Meservie", "birth_date": "1842", "birth_place": "Maine"},
    ]
    candidates = find_duplicate_candidates(people, threshold=85)
    assert len(candidates) == 1


def test_duplicate_detection_ignores_distinct_people():
    people = [
        {"person_id": "1", "full_name": "Daniel Smith Meservie", "birth_date": "1842"},
        {"person_id": "2", "full_name": "Ann Reed Soper", "birth_date": "1825"},
    ]
    assert find_duplicate_candidates(people, threshold=85) == []


def test_duplicate_detection_rejects_same_name_different_generation_years():
    people = [
        {
            "person_id": "1",
            "full_name": "Joseph Fernald",
            "birth_date": "1843",
            "birth_place": "Maine",
            "generation": 4,
            "relationship_to_root": "direct ancestor",
        },
        {
            "person_id": "2",
            "full_name": "Joseph Fernald",
            "birth_date": "1704",
            "birth_place": "Maine",
            "generation": 9,
            "relationship_to_root": "direct ancestor",
        },
    ]
    assert find_duplicate_candidates(people, threshold=85) == []
