from src.relationship_validation import _ancestor_cycle_nodes


def test_ancestor_cycle_nodes_detects_cycle():
    graph = {
        "child": {"parent"},
        "parent": {"grandparent"},
        "grandparent": {"child"},
    }
    assert _ancestor_cycle_nodes(graph) == {"child", "parent", "grandparent"}


def test_ancestor_cycle_nodes_allows_tree():
    graph = {
        "child": {"parent1", "parent2"},
        "parent1": {"grandparent"},
    }
    assert _ancestor_cycle_nodes(graph) == set()

