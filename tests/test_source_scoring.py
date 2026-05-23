from src.source_scoring import confidence_label, score_evidence, source_site


def test_confidence_label_boundaries():
    assert confidence_label(95) == "High confidence"
    assert confidence_label(70) == "Medium-high confidence"
    assert confidence_label(50) == "Medium confidence"
    assert confidence_label(30) == "Low confidence"
    assert confidence_label(10) == "Weak clue only"


def test_score_penalizes_tree_only_sources():
    score, label = score_evidence(
        source_title="Ancestry Family Trees",
        source_url="https://example.com",
        claimed_facts="unsourced tree only",
        pilot_confidence="medium",
    )
    assert score < 60
    assert label in {"Low confidence", "Medium confidence"}


def test_source_site_extracts_domain():
    assert source_site("https://www.familysearch.org/tree/person/details/ABC") == "familysearch.org"

