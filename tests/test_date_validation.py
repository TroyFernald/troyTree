from src.date_validation import find_date_issues, parse_genealogy_date


def test_parse_genealogy_date_handles_common_formats():
    assert parse_genealogy_date("11 November 1842").year == 1842
    assert parse_genealogy_date("1910 Aug 13").month == 8
    assert parse_genealogy_date("26 Sep 1671?").year == 1671
    assert parse_genealogy_date("sept 27,1889").year == 1889
    assert parse_genealogy_date("16 JUN") is None


def test_find_date_issues_flags_death_before_birth():
    issues = find_date_issues("1900", "1899")
    assert any(issue.field == "death_date" for issue in issues)


def test_find_date_issues_flags_implausible_lifespan():
    issues = find_date_issues("1800", "1920")
    assert any("115" in issue.message for issue in issues)
