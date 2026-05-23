"""Public web research helpers.

This module intentionally does not scrape account-gated sites or make tree edits.
Future work can add compliant public-search integrations that write candidate
evidence rows for human review.
"""

from .research_queue import build_search_terms


def suggested_public_searches(person: dict) -> list[str]:
    return build_search_terms(person)

