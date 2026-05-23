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

