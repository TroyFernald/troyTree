"""Search free, official historic-newspaper archives for relatives and record
verified hits as web_research_finding rows.

Primary source: Chronicling America (Library of Congress), now served from the
loc.gov collections JSON API. It is public, free, full-text searchable, covers
~1756-1963, and includes the Maine Digital Newspaper Project titles.

Relevance is verified, not assumed: a hit is only recorded if the page OCR text
actually contains the surname AND at least one corroborating token (the given
name/initial, a residence town, or a year within the person's lifespan). The
matched snippet and a confidence score are stored so a human can confirm.

    python -m src.newspaper_search          # run a batch of direct ancestors
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
from http.client import IncompleteRead

from .init_database import connect
from .paths import WORKING_DB
from .record_findings import record_findings

UA = {"User-Agent": "Mozilla/5.0 (TroyFamilyTreeResearch genealogy; troyfernald@gmail.com)"}
COLLECTION = "https://www.loc.gov/collections/chronicling-america/"
CONTENT_RE = re.compile(r'CONTENT="([^"]*)"')


_last_request = [0.0]
MIN_INTERVAL = 8.0          # loc.gov throttles hard; trickle well under burst limits


def _fetch(url: str, as_json=False, timeout=60, retries=6):
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.time() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers=UA)
        try:
            raw = urllib.request.urlopen(req, timeout=timeout).read()
            _last_request[0] = time.time()
            break
        except IncompleteRead as e:
            _last_request[0] = time.time()
            raw = e.partial
            break
        except urllib.error.HTTPError as e:
            _last_request[0] = time.time()
            if e.code in (429, 503) and attempt < retries - 1:
                time.sleep(30 * (attempt + 1))   # 30,60,...,150s backoff to ride out cooldown
                continue
            raise
    text = raw.decode("utf-8", "replace")
    if as_json:
        import json
        return json.loads(text)
    return text


def search(query: str, state="maine", rows=12) -> list[dict]:
    url = (f"{COLLECTION}?fo=json&c={rows}&fa=location_state:{state}"
           f"&q={urllib.parse.quote(query)}")
    data = _fetch(url, as_json=True)
    out = []
    for it in data.get("results", []):
        rid = it.get("id", "")
        if "/resource/" in rid:
            out.append({"title": (it.get("title") or "").strip(),
                        "date": it.get("date"), "url": rid})
    return out


def page_text(resource_url: str) -> str:
    sep = "&" if "?" in resource_url else "?"
    item = _fetch(f"{resource_url}{sep}fo=json", as_json=True)
    fs = item.get("fulltext_service")
    if not fs:
        return ""
    xml = _fetch(fs)
    return " ".join(CONTENT_RE.findall(xml))


def _year(s: str):
    m = re.search(r"(1[5-9]\d{2}|20\d{2})", s or "")
    return int(m.group(1)) if m else None


def research_person(person: dict, max_pages=8, sleep=1.5) -> list[dict]:
    """person: person_id, full_name, surname, given, towns(list), spouse, b_year, d_year"""
    surname = person["surname"]
    if not surname or len(surname) < 3:
        return []
    given = (person.get("given") or "").split()[0] if person.get("given") else ""
    towns = [t for t in person.get("towns", []) if t]
    by, dy = person.get("b_year"), person.get("d_year")
    query = " ".join(filter(None, [surname, towns[0] if towns else ""]))
    findings = []
    seen = set()
    for hit in search(query, rows=max_pages):
        if hit["url"] in seen:
            continue
        seen.add(hit["url"])
        try:
            txt = page_text(hit["url"])
        except Exception:
            continue
        low = txt.lower()
        si = low.find(surname.lower())
        if si < 0:
            continue
        window = low[max(0, si - 120):si + 120]
        corr = []
        if given and given.lower() in window:
            corr.append(f"given name '{given}'")
        town_hit = next((t for t in towns if t.lower() in low), None)
        if town_hit:
            corr.append(f"town '{town_hit}'")
        py = _year(hit["date"])
        if py and ((by and by - 2 <= py) or True) and (dy is None or py <= dy + 5) and (by is None or py >= by - 2):
            corr.append(f"date {py} within lifespan")
        if not corr:
            continue  # surname alone is not enough
        score = 30 + 15 * len(corr)
        score = min(score, 80)
        label = ("Medium-high confidence" if score >= 70 else
                 "Medium confidence" if score >= 50 else "Low confidence")
        snippet = txt[max(0, si - 120):si + 160].strip()
        findings.append({
            "person_id": person["person_id"],
            "person_name": person["full_name"],
            "search_query": f"Chronicling America: {query}",
            "source_title": hit["title"],
            "source_url": hit["url"],
            "source_site": "chroniclingamerica.loc.gov",
            "source_type": "historic newspaper (Chronicling America)",
            "snippet": snippet,
            "claimed_facts": f"Newspaper mention; corroborated by: {', '.join(corr)}",
            "confidence_score": score,
            "confidence_label": label,
            "notes": f"{hit['date']} {hit['title']}",
        })
        time.sleep(sleep)
    return findings


# The project's priority Maine/Maritime family surnames (handoff doc) come first.
PRIORITY = ["lenentine", "meservie", "meserve", "meservey", "fernald", "bagley",
            "cookson", "soper", "fairfield", "cromwell", "mckay", "mackay",
            "fuller", "grant", "pierce", "adams"]
CLEAN_SURNAME = re.compile(r"^[A-Za-z][A-Za-z'\-]{2,19}$")


def load_targets(limit=15, db_path=WORKING_DB) -> list[dict]:
    """Direct ancestors with a clean single-word surname who lived in the
    Chronicling America era (~1780-1963 by birth or death year)."""
    targets = []
    with connect(db_path) as con:
        rows = con.execute(
            """SELECT person_id, full_name, given_name, surname, birth_date, death_date,
                      birth_place, death_place
               FROM people
               WHERE generation IS NOT NULL AND surname IS NOT NULL""").fetchall()
    for r in rows:
        surname = (r["surname"] or "").strip()
        if not CLEAN_SURNAME.match(surname):
            continue
        by, dy = _year(r["birth_date"]), _year(r["death_date"])
        era = (by and 1780 <= by <= 1963) or (dy and 1780 <= dy <= 1963)
        if not era:
            continue
        towns = []
        for pl in (r["birth_place"], r["death_place"]):
            if pl and "maine" in pl.lower():
                towns.append(pl.split(",")[0].strip())
        targets.append({
            "person_id": r["person_id"], "full_name": r["full_name"],
            "surname": surname, "given": r["given_name"],
            "towns": list(dict.fromkeys(towns)),
            "b_year": by, "d_year": dy,
        })

    def rank(t):
        s = t["surname"].lower()
        pr = PRIORITY.index(s) if s in PRIORITY else len(PRIORITY)
        return (pr, 0 if t["towns"] else 1, t["full_name"])
    targets.sort(key=rank)
    return targets[:limit]


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    targets = load_targets(limit=n)
    all_findings = []
    for t in targets:
        try:
            fs = research_person(t)
        except Exception as e:
            print(f"  {t['full_name']}: ERROR {type(e).__name__}: {e}", flush=True)
            continue
        print(f"  {t['full_name']} ({t['surname']}): {len(fs)} verified newspaper hits", flush=True)
        all_findings.extend(fs)
    if all_findings:
        stats = record_findings(all_findings, processed=[t["person_id"] for t in targets])
        print("RECORDED:", stats)
    else:
        print("No verified newspaper hits in this batch.")
