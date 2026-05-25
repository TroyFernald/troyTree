"""Assemble the publishable static site for Vercel.

Runs every view generator, then collects just the publishable output (the view
HTML pages + the one vendored JS lib) plus a landing page into a clean
``troy-family-site/`` folder that can be its own private GitHub repo. Vercel
deploys it on push; Cloudflare fronts the domain and password.

Deliberately bloat-safe: the folder contains **no** database and **no** media
(909 MB of photos live in Cloudflare R2; pass their public base URL as
``media_base`` so photo links resolve on the web). Living people are redacted by
default — pass ``redact_living=False`` to publish everyone.

    python -m src.build_site                          # local build, photos relative
    python -m src.build_site https://media.troytree.org/   # photos from R2
"""

from __future__ import annotations

import json
import os
import shutil
import sys

from . import (build_castles, build_fan_chart, build_gallery, build_graph_3d,
               build_guide, build_html_viewer, build_map, build_mcp_page,
               build_notable, build_review, build_storybook)
from .ancestral_sides import compute_sides
from .init_database import connect
from .paths import EXPORTS_DIR, PROJECT_ROOT, WORKING_DB

DEFAULT_SITE_DIR = PROJECT_ROOT.parent / "troy-family-site"
VIEW_FILES = ["family.html", "graph_3d.html", "fan.html", "story.html", "map.html",
              "notable.html", "castles.html", "gallery.html", "review.html", "guide.html",
              "connect.html"]


def _site_password() -> str:
    """Shared family password for the site gate, from env or a gitignored file.
    Returns "" if none configured (then no gate is written)."""
    env = os.environ.get("SITE_PASSWORD")
    if env:
        return env.strip()
    f = PROJECT_ROOT / "data" / "site_password.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


def build_site(media_base: str = "", redact_living: bool = True, out_dir=DEFAULT_SITE_DIR,
               archive_url: str = "") -> dict:
    build_storybook.build(redact_living=redact_living, media_base=media_base)  # writes story_ids.json first
    build_html_viewer.build(redact_living=redact_living, media_base=media_base)
    build_graph_3d.build(redact_living=redact_living)
    build_fan_chart.build(redact_living=redact_living)
    build_map.build(redact_living=redact_living)
    build_notable.build()
    build_castles.build()
    build_gallery.build(media_base=media_base)
    build_review.build()
    build_guide.build()
    build_mcp_page.build()

    with connect(WORKING_DB) as con:
        _, side_labels, side_keys = compute_sides(con)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name in VIEW_FILES:
        shutil.copy2(EXPORTS_DIR / name, out_dir / name)
    shutil.copytree(EXPORTS_DIR / "lib", out_dir / "lib", dirs_exist_ok=True)

    (out_dir / "index.html").write_text(
        _LANDING.replace("__SIDELABELS__", json.dumps(side_labels))
                .replace("__SIDEKEYS__", json.dumps(side_keys))
                .replace("__ARCHIVEURL__", json.dumps(archive_url)),
        encoding="utf-8",
    )
    (out_dir / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    (out_dir / "README.md").write_text(_README, encoding="utf-8")
    # Cloudflare Pages: always revalidate HTML so visitors get the latest build (304 if
    # unchanged), while the big vendored JS lib can cache for a year by its stable name.
    (out_dir / "_headers").write_text(
        "/*\n  Cache-Control: no-cache\n/lib/*\n  Cache-Control: public, max-age=31536000, immutable\n",
        encoding="utf-8",
    )

    # Password gate (Cloudflare Pages advanced-mode worker). Written only when a
    # password is configured; keeps the whole site behind a shared family password.
    password = _site_password()
    if password:
        (out_dir / "_worker.js").write_text(_WORKER.replace("__PASSWORD__", json.dumps(password)), encoding="utf-8")

    return {
        "out": str(out_dir),
        "files": VIEW_FILES + ["index.html", "lib/3d-force-graph.min.js"],
        "media_base": media_base or "(relative — set R2 URL for web photos)",
        "redact_living": redact_living,
    }


_LANDING = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree</title>
<style>
  :root { --bg:#f4efe7; --ink:#3a2f25; --accent:#7a5c3e; --card:#fff; --line:#e3dac9; }
  * { box-sizing:border-box; }
  body { margin:0; min-height:100vh; background:
      radial-gradient(circle at 50% -10%, #fbf7f0, var(--bg)); color:var(--ink);
    font:16px/1.55 Georgia,"Times New Roman",serif; display:flex; flex-direction:column; align-items:center; }
  header { text-align:center; padding:46px 20px 10px; }
  header h1 { font-size:38px; margin:0; letter-spacing:.5px; }
  header p { color:#8a7866; margin:8px 0 0; font-size:16px; }
  .sides { display:flex; gap:10px; margin:26px 0 8px; flex-wrap:wrap; justify-content:center; }
  .sides button { font:inherit; font-size:15px; padding:9px 20px; border-radius:24px; cursor:pointer;
    border:1px solid var(--line); background:#fff; color:var(--ink); }
  .sides button.on { background:var(--accent); color:#fff; border-color:var(--accent); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:18px;
    width:100%; max-width:860px; padding:24px 20px 60px; }
  a.card { display:block; text-decoration:none; color:inherit; background:var(--card);
    border:1px solid var(--line); border-radius:14px; padding:22px; transition:transform .12s, box-shadow .12s; }
  a.card:hover { transform:translateY(-3px); box-shadow:0 10px 26px rgba(90,70,50,.14); }
  a.card .ico { font-size:30px; }
  a.card h2 { font-size:19px; margin:10px 0 4px; }
  a.card p { margin:0; color:#8a7866; font-size:14px; }
  a.card.soon { opacity:.5; pointer-events:none; }
  footer { color:#a3937f; font-size:13px; padding-bottom:30px; }
  #dlwrap { display:none; margin:0 0 24px; }
  .dlbtn { display:inline-block; background:#7a5c3e; color:#fff; text-decoration:none;
    padding:11px 22px; border-radius:24px; font-size:15px; }
  .dlbtn:hover { background:#624829; }
</style>
</head>
<body>
<header>
  <h1>Troy Family Tree</h1>
  <p id="tag">Choose a side of the family, then explore</p>
  <div class="sides" id="sides"></div>
</header>
<div class="grid" id="grid">
  <a class="card" data-view="family.html"><div class="ico">📇</div><h2>Browse</h2><p>Every person, searchable, with photos, documents and findings.</p></a>
  <a class="card" data-view="notable.html"><div class="ico">⭐</div><h2>Notable Ancestors</h2><p>Mayflower passengers, war service, and the royal & noble legends.</p></a>
  <a class="card" data-view="castles.html"><div class="ico">🏰</div><h2>Ancestral Castles</h2><p>The castles and great houses of our noble lines, as they stand today.</p></a>
  <a class="card" data-view="gallery.html"><div class="ico">🖼️</div><h2>Photo Gallery</h2><p>Every photograph and document in the archive, in one place.</p></a>
  <a class="card" data-view="graph_3d.html"><div class="ico">🕸️</div><h2>3D Connections</h2><p>The whole tree as a rotating 3D web of relationships.</p></a>
  <a class="card" data-view="fan.html"><div class="ico">🌓</div><h2>Fan Chart</h2><p>Your direct ancestors in concentric 360° rings.</p></a>
  <a class="card" data-view="map.html"><div class="ico">🗺️</div><h2>World Map</h2><p>Where the family lived, mapped across the world.</p></a>
  <a class="card" data-view="story.html"><div class="ico">📖</div><h2>Storybook</h2><p>Each life as a narrative you can page through.</p></a>
  <a class="card" data-view="guide.html"><div class="ico">🧭</div><h2>Research Guide</h2><p>Where to look next — the best archives and records for our lines.</p></a>
  <a class="card" data-view="review.html"><div class="ico">🛠️</div><h2>Review &amp; Corrections</h2><p>Open questions, possible duplicates, and dates to double-check.</p></a>
  <a class="card" data-view="connect.html"><div class="ico">🤖</div><h2>Ask the AI</h2><p>Connect your own AI assistant and ask the family database questions.</p></a>
</div>
<p id="dlwrap"><a id="dl" class="dlbtn" download>⬇ Download the whole archive (offline backup)</a></p>
<footer>troytree.org · private family archive</footer>
<script>
const SIDE_LABELS = __SIDELABELS__, SIDE_KEYS = __SIDEKEYS__;
let side = new URLSearchParams(location.search).get('side') || '';
const sidesEl = document.getElementById('sides');
const opts = [['','Both sides']].concat(SIDE_KEYS.map(k=>[k, SIDE_LABELS[k]+' side']));
function render() {
  sidesEl.innerHTML = opts.map(([v,l])=>`<button data-v="${v}" class="${v===side?'on':''}">${l}</button>`).join('');
  const q = side ? ('?side='+encodeURIComponent(side)) : '';
  document.querySelectorAll('a.card[data-view]').forEach(a => a.href = a.dataset.view + q);
}
sidesEl.addEventListener('click', e => { const b=e.target.closest('button'); if(b){ side=b.dataset.v; render(); }});
render();
const ARCHIVE_URL = __ARCHIVEURL__;
if (ARCHIVE_URL) { document.getElementById('dl').href = ARCHIVE_URL; document.getElementById('dlwrap').style.display = 'block'; }
</script>
</body>
</html>
"""

_GITIGNORE = (
    ".DS_Store\nThumbs.db\n*.sqlite\n*.db\n__pycache__/\nnode_modules/\n"
    "\n# wrangler files\n.wrangler\n.dev.vars*\n!.dev.vars.example\n.env*\n!.env.example\n"
)

_README = """# Troy Family Tree — published site

Static family-history site for **troytree.org**.

- Generated from the research database by `src/build_site.py` (do not hand-edit the HTML).
- Deployed by **Cloudflare Pages** on push; DNS, photos (R2), and password (Access) all via **Cloudflare**.
- Photos are served from **Cloudflare R2**, not this repo. The database and media are intentionally NOT committed here (keeps the repo small).
- Living people are redacted unless the site was built with `redact_living=False`.

Rebuild: `python -m src.build_site https://<your-r2-public-base>/`
"""

_WORKER = r"""// Cloudflare Pages advanced-mode worker: gate the whole site behind a shared
// family password, then serve the static assets. Worker source is not exposed
// to browsers. Password is injected at build time from a gitignored local file.
export default {
  async fetch(request, env) {
    const PASSWORD = __PASSWORD__;
    const auth = request.headers.get("Authorization") || "";
    if (auth.startsWith("Basic ")) {
      try {
        const decoded = atob(auth.slice(6));
        if (decoded.slice(decoded.indexOf(":") + 1) === PASSWORD) {
          return env.ASSETS.fetch(request);
        }
      } catch (e) { /* fall through */ }
    }
    return new Response("Troy Family Tree - enter the family password.", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="Troy Family Tree (any name + family password)"' },
    });
  },
};
"""


if __name__ == "__main__":
    media = sys.argv[1] if len(sys.argv) > 1 else ""
    print(build_site(media_base=media))
