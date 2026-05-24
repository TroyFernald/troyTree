from src.privacy import is_living


def test_recorded_death_is_not_living():
    assert is_living("1850", "1908") is False


def test_recent_birth_no_death_is_living():
    assert is_living("1990", "") is True


def test_old_birth_no_death_is_not_living():
    assert is_living("1850", "") is False


def test_unknown_birth_recent_generation_is_living():
    assert is_living("", "", generation=0) is True
    assert is_living("", "", generation=1) is True


def test_unknown_birth_deep_generation_is_not_living():
    assert is_living("", "", generation=8) is False
