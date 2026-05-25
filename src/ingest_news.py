"""Newspaper-clipping dropbox: OCR subscription clippings and attach them to people.

Workflow (for clippings you save from Newspapers.com / GenealogyBank / etc.):

  1. Drop image or PDF files into  C:\\Tree\\news_dropbox\\
     (optionally name them with a hint, e.g.  Fernald-John_1912_BangorDailyNews.jpg)
  2. Run:   python -m src.ingest_news ocr
     -> OCRs every new file with Tesseract and writes  news_dropbox/_review.json
        with the extracted text plus suggested people (matched by surname) and a
        guessed paper + date.
  3. I review _review.json, then call add_clipping(...) for each, which:
       - inserts a 'newspaper' finding so the text shows in the Storybook
         "In the newspapers" section for that person, and
       - imports the clipping image into the media library, linked to the person,
         so the actual clipping is viewable in the gallery and storybook.
  4. Rebuild + deploy (tools/refresh.ps1 or build_site).

Nothing is fabricated: only text Tesseract actually read from a real clipping you
supplied is stored.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

import pytesseract
from PIL import Image

from .init_database import connect
from .paths import WORKING_DB

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DROPBOX = Path(r"C:\Tree\news_dropbox")
PROCESSED = DROPBOX / "_processed"
REVIEW = DROPBOX / "_review.json"
MEDIA_DIR = Path(r"C:\Tree\ancestory-import_media")          # canonical media store
PUB_MEDIA = Path(r"C:\troytree-dist\pub\media")              # served copy
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif"}

PAPERS = [
    ("bangor", "Bangor Daily News"),
    ("republican journal", "Belfast Republican Journal"),
    ("belfast", "Belfast Republican Journal"),
    ("waterville", "Waterville Sentinel"),
    ("portland", "Portland Press Herald"),
    ("kennebec", "Kennebec Journal"),
    ("ellsworth", "Ellsworth American"),
]
_YEAR = re.compile(r"\b(1[6-9]\d\d|20[0-2]\d)\b")


def _ordinal(k: int) -> str:
    return f"{k}th" if 10 <= k % 100 <= 20 else {1: f"{k}st", 2: f"{k}nd", 3: f"{k}rd"}.get(k % 10, f"{k}th")


def relationship(gen, fem=None) -> str:
    if gen is None:
        return "relative"
    if gen == 0:
        return "you"
    word = "mother" if fem else "father" if fem is False else "parent"
    if gen == 1:
        return f"your {word}"
    base = "grand" + word
    greats = gen - 2
    if greats == 0:
        return f"your {base}"
    if greats == 1:
        return f"your great-{base}"
    return f"your {_ordinal(greats)} great-{base}"


def _ocr_image(path: Path) -> str:
    with Image.open(path) as img:
        return (pytesseract.image_to_string(img) or "").strip()


def _ocr_pdf(path: Path) -> str:
    """Best-effort PDF OCR. Uses pypdfium2 (no external deps) if available."""
    try:
        import pypdfium2 as pdfium
    except Exception:
        return ""
    out = []
    pdf = pdfium.PdfDocument(str(path))
    for i in range(len(pdf)):
        bmp = pdf[i].render(scale=3).to_pil()
        out.append((pytesseract.image_to_string(bmp) or "").strip())
    return "\n\n".join(t for t in out if t).strip()


def _guess_paper(text: str, fname: str) -> str:
    hay = (text + " " + fname).lower()
    for key, name in PAPERS:
        if key in hay:
            return name
    return ""


def _guess_date(text: str, fname: str) -> str:
    m = _YEAR.search(fname) or _YEAR.search(text)
    return m.group(0) if m else ""


def _people_index(con):
    rows = con.execute(
        "SELECT person_id, full_name, surname, given_name, generation, relationship_to_root, notes "
        "FROM people WHERE surname IS NOT NULL AND surname<>''"
    ).fetchall()
    return rows


def _suggest(text: str, fname: str, people) -> list[dict]:
    hay = (text + " " + fname).lower()
    hits = []
    for r in people:
        sur = (r["surname"] or "").lower().strip()
        if len(sur) < 3:
            continue
        if re.search(r"\b" + re.escape(sur) + r"\b", hay):
            given = (r["given_name"] or "").split(" ")[0].lower()
            score = 2 if given and given in hay else 1
            gen = r["generation"]
            # grandparents / great-grandparents are what the user is after
            if gen is not None and 1 <= gen <= 5:
                score += 3
            hits.append((score, gen if gen is not None else 99, r))
    hits.sort(key=lambda t: (-t[0], t[1]))
    out = []
    for _, _, r in hits[:6]:
        out.append({"person_id": r["person_id"], "name": r["full_name"],
                    "gen": r["generation"], "rel": relationship(r["generation"])})
    return out


def ocr_dropbox(db_path=WORKING_DB) -> dict:
    DROPBOX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(exist_ok=True)
    files = [p for p in DROPBOX.iterdir()
             if p.is_file() and not p.name.startswith("_")
             and p.suffix.lower() in (IMAGE_EXTS | {".pdf"})]
    review = []
    if REVIEW.exists():
        try:
            review = json.loads(REVIEW.read_text(encoding="utf-8"))
        except Exception:
            review = []
    done_files = {e["file"] for e in review}
    with connect(db_path) as con:
        people = _people_index(con)
    new = 0
    for p in files:
        if p.name in done_files:
            continue
        try:
            text = _ocr_pdf(p) if p.suffix.lower() == ".pdf" else _ocr_image(p)
        except Exception as e:
            text = f"(OCR error: {e})"
        review.append({
            "file": p.name,
            "paper_guess": _guess_paper(text, p.name),
            "date_guess": _guess_date(text, p.name),
            "suggested_people": _suggest(text, p.name, people),
            "ocr_text": text,
            "ingested": False,
        })
        new += 1
        print(f"  OCR'd {p.name}: {len(text)} chars, "
              f"{len(review[-1]['suggested_people'])} person match(es)", flush=True)
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"new_files": new, "total_in_review": len(review), "review_file": str(REVIEW)}


def add_clipping(person_id: str, paper: str, when: str, text: str,
                 image: str | None = None, url: str = "", db_path=WORKING_DB) -> dict:
    """Insert a newspaper finding (shows in the Storybook) and, if an image file
    name in the dropbox is given, import it as media linked to the person."""
    with connect(db_path) as con:
        pr = con.execute("SELECT full_name FROM people WHERE person_id=?", (person_id,)).fetchone()
        if pr is None:
            raise SystemExit(f"No such person_id: {person_id}")
        pname = pr["full_name"]
        title = paper + (f" — {when}" if when else "")
        # Import the source file first, so its served /media/ URL can be the clickable source.
        media_done = None
        served_url = ""
        if image:
            src = DROPBOX / image
            if not src.exists():
                raise SystemExit(f"File not found in dropbox: {src}")
            ext = src.suffix.lower()
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", f"news_{person_id.strip('@')}_{image}")
            MEDIA_DIR.mkdir(parents=True, exist_ok=True)
            dst = MEDIA_DIR / safe
            shutil.copy2(src, dst)
            if PUB_MEDIA.exists():
                shutil.copy2(src, PUB_MEDIA / safe)
            served_url = "/media/" + safe
            md5 = hashlib.md5(dst.read_bytes()).hexdigest()
            kind = "photo" if ext in {".jpg", ".jpeg", ".png"} else "document"
            row = con.execute("SELECT media_id FROM media_object WHERE md5=?", (md5,)).fetchone()
            if row:                                  # same file already imported (shared by several people)
                mid = row["media_id"]
            else:
                cur = con.execute(
                    "INSERT INTO media_object (file_name, file_path, file_ext, file_size, md5, caption, "
                    "media_date, kind, owner_count, ocr_text, ocr_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (safe, str(dst), ext, dst.stat().st_size, md5, title, when, kind, 1, text.strip(), "done"),
                )
                mid = cur.lastrowid
            if not con.execute("SELECT 1 FROM media_person_link WHERE media_id=? AND person_id=?",
                               (mid, person_id)).fetchone():
                con.execute(
                    "INSERT INTO media_person_link (media_id, person_id, person_name, link_type) "
                    "VALUES (?,?,?,?)", (mid, person_id, pname, "newspaper"),
                )
            media_done = safe
        final_url = url or served_url            # clickable source = the PDF/image when given
        con.execute(
            "INSERT OR REPLACE INTO web_research_finding (person_id, person_name, search_query, source_title, "
            "source_type, source_url, source_site, snippet, claimed_facts, confidence_score, "
            "confidence_label, review_status, date_found, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (person_id, pname, "news_dropbox", title, "newspaper", final_url, paper,
             text.strip(), text.strip()[:200], 0.95, "user-supplied", "verified",
             date.today().isoformat(), when),
        )
        # mark review entry ingested
        if REVIEW.exists():
            rev = json.loads(REVIEW.read_text(encoding="utf-8"))
            for e in rev:
                if image and e["file"] == image:
                    e["ingested"] = True
            REVIEW.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"person": pname, "paper": title, "image_imported": media_done}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ocr"
    if cmd == "ocr":
        print(ocr_dropbox())
    else:
        print("Usage: python -m src.ingest_news ocr")
