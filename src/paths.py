from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ORIGINAL_DIR = DATA_DIR / "original"
WORKING_DIR = DATA_DIR / "working"
EXPORTS_DIR = DATA_DIR / "exports"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
CONFIG_DIR = PROJECT_ROOT / "config"

PILOT_DB = ORIGINAL_DIR / "troy_tree_research_pilot.sqlite"
WORKING_DB = WORKING_DIR / "research.sqlite"


def ensure_directories() -> None:
    for path in (ORIGINAL_DIR, WORKING_DIR, EXPORTS_DIR, SNAPSHOTS_DIR):
        path.mkdir(parents=True, exist_ok=True)

