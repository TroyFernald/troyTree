from src.notable_people import _candidate_rows


class Row(dict):
    def __getitem__(self, key):
        return self.get(key)

    def keys(self):
        return super().keys()


def test_notable_detector_finds_mayflower_name():
    row = Row(
        full_name="John Alden",
        birth_place="England",
        death_place="Duxbury, Plymouth, Massachusetts",
        notes="",
        generation=12,
    )
    candidates = _candidate_rows(row)
    assert any(candidate["category"] == "mayflower" for candidate in candidates)


def test_notable_detector_flags_royal_claim_as_high_risk():
    row = Row(
        full_name="Louis Capet King of France",
        birth_place="France",
        death_place="France",
        notes="",
        generation=15,
    )
    candidates = _candidate_rows(row)
    assert any(candidate["category"] in {"royal_noble", "medieval_descent"} for candidate in candidates)
    assert any(candidate["risk_level"] == "high" for candidate in candidates)

