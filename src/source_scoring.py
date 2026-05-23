from __future__ import annotations

import re

RECORD_TERMS = (
    "birth record",
    "marriage record",
    "death record",
    "census",
    "probate",
    "town record",
    "church record",
    "military",
    "obituary",
    "newspaper",
    "register",
)

WEAK_TERMS = (
    "ancestry family trees",
    "geneanet",
    "personal genealogy",
    "noble",
    "medieval",
    "unsourced",
)


def confidence_label(score: int) -> str:
    if score >= 90:
        return "High confidence"
    if score >= 70:
        return "Medium-high confidence"
    if score >= 50:
        return "Medium confidence"
    if score >= 30:
        return "Low confidence"
    return "Weak clue only"


def source_site(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    return match.group(1).lower() if match else ""


def infer_source_type(title: str, url: str, evidence_type: str = "") -> str:
    text = f"{title} {url} {evidence_type}".lower()
    if "familysearch" in text:
        return "FamilySearch public profile"
    if "wikitree" in text:
        return "WikiTree profile"
    if "findagrave" in text or "find a grave" in text:
        return "Find a Grave memorial"
    if "genealogy" in text or "familygenes" in text:
        return "Personal genealogy page"
    if any(term in text for term in RECORD_TERMS):
        return "Record-based source"
    return "Web evidence lead"


def score_evidence(
    *,
    source_title: str,
    source_url: str,
    evidence_type: str = "",
    claimed_facts: str = "",
    pilot_confidence: str = "",
) -> tuple[int, str]:
    text = f"{source_title} {source_url} {evidence_type} {claimed_facts}".lower()
    score = 40

    if "medium-high" in pilot_confidence.lower():
        score += 25
    elif "medium" in pilot_confidence.lower():
        score += 15
    elif "low" in pilot_confidence.lower():
        score += 5

    if any(term in text for term in RECORD_TERMS):
        score += 18
    if "familysearch" in text:
        score += 10
    if "wikitree" in text:
        score += 5
    if "findagrave" in text or "find a grave" in text:
        score += 6
    if "spouse" in text or "married" in text:
        score += 8
    if "father" in text or "mother" in text or "parents" in text:
        score += 8
    if "children" in text or "child" in text:
        score += 5
    if "matches your tree" in text or "match" in evidence_type.lower():
        score += 8

    if "conflict" in text:
        score -= 10
    if any(term in text for term in WEAK_TERMS):
        score -= 10
    if "noble" in text or "medieval" in text:
        score -= 25

    score = max(0, min(100, score))
    return score, confidence_label(score)

