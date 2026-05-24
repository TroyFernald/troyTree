"""OCR the document-scan media (census pages, certificates, wills, newspaper
clippings, etc.) into searchable text stored on each media_object row.

Image documents are read with Tesseract. The extracted text becomes the basis
for evidence (see media_to_evidence) so a saved record turns into a citable,
searchable assertion attached to the people the media is linked to.
"""

from __future__ import annotations

import sqlite3
import sys

import pytesseract
from PIL import Image

from .paths import WORKING_DB

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif"}


def run_ocr(db_path=WORKING_DB, limit: int | None = None) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT media_id, file_path, file_ext FROM media_object "
        "WHERE kind='document' AND ocr_status='pending' ORDER BY media_id"
    ).fetchall()
    if limit:
        rows = rows[:limit]
    stats = {"total": len(rows), "ocr_done": 0, "empty": 0, "skipped_format": 0, "error": 0}
    for i, r in enumerate(rows, 1):
        if r["file_ext"] not in IMAGE_EXTS:
            con.execute("UPDATE media_object SET ocr_status='skipped_format' WHERE media_id=?", (r["media_id"],))
            stats["skipped_format"] += 1
            continue
        try:
            with Image.open(r["file_path"]) as img:
                text = pytesseract.image_to_string(img)
            text = (text or "").strip()
            status = "done" if text else "empty"
            con.execute("UPDATE media_object SET ocr_text=?, ocr_status=? WHERE media_id=?",
                        (text, status, r["media_id"]))
            stats["ocr_done" if text else "empty"] += 1
        except Exception as e:
            con.execute("UPDATE media_object SET ocr_status='error', ocr_text=? WHERE media_id=?",
                        (f"OCR error: {e}", r["media_id"]))
            stats["error"] += 1
        if i % 25 == 0:
            con.commit()
            print(f"  ...{i}/{len(rows)} processed", flush=True)
    con.commit()
    con.close()
    return stats


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(run_ocr(limit=lim))
