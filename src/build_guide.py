"""Build ``guide.html`` — the family research guide / "where to look next".

Renders ``data/exports/research_plan.md`` to a clean, mobile-friendly reading
page using the vendored marked.js. The markdown is embedded directly in the
page (no fetch) so it works offline and behind the password gate.

    python -m src.build_guide
"""

from __future__ import annotations

import json

from .paths import EXPORTS_DIR, WORKING_DB

OUT_PATH = EXPORTS_DIR / "guide.html"
PLAN_PATH = EXPORTS_DIR / "research_plan.md"

_FALLBACK = "# Research Guide\n\n_The research plan has not been generated yet._\n"


def build(db_path=WORKING_DB) -> dict:
    md = PLAN_PATH.read_text(encoding="utf-8") if PLAN_PATH.exists() else _FALLBACK
    html_doc = _TEMPLATE.replace("__MD__", json.dumps(md, ensure_ascii=False).replace("</", "<\\/"))
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"chars": len(md), "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree · Research Guide</title>
<script src="lib/marked.min.js"></script>
<style>
  :root{--bg:#f4efe7;--ink:#3a2f25;--accent:#7a5c3e;--line:#e3dac9;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 Georgia,"Times New Roman",serif;}
  header{padding:16px 18px 6px;font-family:-apple-system,Segoe UI,Roboto,sans-serif;}
  header a.home{color:var(--accent);text-decoration:none;font-size:14px;}
  .doc{max-width:760px;margin:0 auto;padding:8px 22px 80px;}
  .doc h1{font-size:30px;line-height:1.2;border-bottom:2px solid var(--line);padding-bottom:8px;}
  .doc h2{font-size:23px;margin-top:1.8em;color:var(--accent);}
  .doc h3{font-size:18px;margin-top:1.4em;}
  .doc a{color:var(--accent);}
  .doc code{background:#ece3d4;padding:1px 5px;border-radius:4px;font-size:.9em;}
  .doc table{border-collapse:collapse;width:100%;margin:1em 0;font-size:14.5px;}
  .doc th,.doc td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top;}
  .doc th{background:#ece3d4;}
  .doc blockquote{border-left:3px solid var(--accent);margin:1em 0;padding:.2em 1em;color:#6b5945;background:#fbf8f2;}
  .doc li{margin:.25em 0;}
  @media (max-width:600px){body{font-size:15px;}.doc{padding:8px 16px 60px;}.doc h1{font-size:25px;}}
</style>
</head>
<body>
<header><a class="home" href="index.html">‹ Home</a></header>
<article class="doc" id="doc"></article>
<script>
const MD=__MD__;
document.getElementById('doc').innerHTML=(window.marked?(marked.parse?marked.parse(MD):marked(MD)):('<pre>'+MD.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))+'</pre>'));
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
