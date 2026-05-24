"""Geocode the free-text birth/death places to coordinates, with a persistent cache.

Uses OpenStreetMap's Nominatim (keyless, free) at the required ≤1 request/second,
identifying the app and caching every lookup (hits and misses) to
``data/exports/geocode_cache.json``. Geocoding is therefore a one-time cost:
later runs only fetch places not already cached, and the map build reads the
cache instantly. Most-mentioned places are fetched first so a bounded run still
covers the bulk of the family.

    python -m src.geocode 400      # geocode up to 400 not-yet-cached places
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request

from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB

CACHE_PATH = EXPORTS_DIR / "geocode_cache.json"
UA = {"User-Agent": "TroyTreeFamilyResearch/1.0 (troyfernald@gmail.com)"}
MIN_INTERVAL = 1.1  # Nominatim usage policy: max 1 request/second


def normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().rstrip(".")


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {}  # tolerate a concurrent mid-write read
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def place_counts(con) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in con.execute(
        "SELECT birth_place p FROM people WHERE birth_place <> '' "
        "UNION ALL SELECT death_place FROM people WHERE death_place <> ''"
    ):
        n = normalize(r["p"])
        if n:
            counts[n] = counts.get(n, 0) + 1
    return counts


def geocode_one(query: str):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"format": "json", "limit": 1, "q": query}
    )
    req = urllib.request.Request(url, headers=UA)
    data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    if data:
        return [round(float(data[0]["lat"]), 5), round(float(data[0]["lon"]), 5)]
    return None


def run(limit: int = 400, db_path=WORKING_DB) -> dict:
    cache = load_cache()
    with connect(db_path) as con:
        counts = place_counts(con)
    todo = [p for p, _ in sorted(counts.items(), key=lambda kv: -kv[1]) if p not in cache][:limit]
    for i, q in enumerate(todo, 1):
        try:
            cache[q] = geocode_one(q)
        except Exception:
            cache[q] = None
        if i % 10 == 0:
            save_cache(cache)
            print(f"  geocoded {i}/{len(todo)}", flush=True)
        time.sleep(MIN_INTERVAL)
    save_cache(cache)
    located = sum(1 for v in cache.values() if v)
    return {"cached": len(cache), "located": located, "this_run": len(todo), "places_total": len(counts)}


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    print(run(lim))
