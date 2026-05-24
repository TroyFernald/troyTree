"""Build a downloadable offline archive of the whole site for family backups.

Produces a self-contained copy where every view references photos at ``media/``
(relative), bundles the actual photo files alongside, and zips it. A relative
unzips it and double-clicks ``index.html`` to browse everything — people, views,
and photos — fully offline, with no dependency on the live site.

The archive is too big for Vercel/Git (it includes ~909 MB of photos), so it is
written to ``C:\\troytree-dist`` (outside the Drive-mirrored project tree) and is
meant to be uploaded to Cloudflare R2; the landing page's Download button then
points at that R2 URL.

    python -m src.build_offline            # build folder + zip
    python -m src.build_offline --nozip    # folder only (skip the slow zip)
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

from .build_site import build_site
from .paths import PROJECT_ROOT

DIST = Path(PROJECT_ROOT.anchor) / "troytree-dist"   # e.g. C:\troytree-dist (not under C:\Tree)
OFFLINE_DIR = DIST / "troytree-offline"
ARCHIVE = DIST / "troytree_family_archive.zip"
MEDIA_SRC = PROJECT_ROOT.parent / "ancestory-import_media"


def build_offline(redact_living: bool = True, include_media: bool = True, make_zip: bool = True) -> dict:
    DIST.mkdir(parents=True, exist_ok=True)
    # Views reference photos relatively at ./media/<file>; no Download button inside the archive.
    build_site(media_base="media/", redact_living=redact_living, out_dir=OFFLINE_DIR, archive_url="")

    copied = 0
    if include_media and MEDIA_SRC.exists():
        dest = OFFLINE_DIR / "media"
        dest.mkdir(parents=True, exist_ok=True)
        for f in MEDIA_SRC.iterdir():
            if f.is_file():
                shutil.copy2(f, dest / f.name)
                copied += 1

    result = {"dir": str(OFFLINE_DIR), "media_files": copied}
    if make_zip:
        if ARCHIVE.exists():
            ARCHIVE.unlink()
        with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as z:
            for p in OFFLINE_DIR.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(OFFLINE_DIR))
        result["archive"] = str(ARCHIVE)
        result["archive_mb"] = round(ARCHIVE.stat().st_size / 1048576, 1)
    return result


if __name__ == "__main__":
    print(build_offline(make_zip="--nozip" not in sys.argv))
