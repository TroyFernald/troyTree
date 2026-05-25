"""Build ``review.html`` — a "Tree Corrections to Review" page for the owner.

Consolidates the actionable issues surfaced across the project into one place:
research conflicts flagged by the agents, candidate duplicate people to merge,
and date/relationship validation issues. Read-only, searchable, tabbed — a
worklist for fixing the actual tree (nothing here changes data automatically).

    python -m src.build_review
"""

from __future__ import annotations

import json

from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB

OUT_PATH = EXPORTS_DIR / "review.html"
CONFLICT_FILTER = (
    "lower(notes) LIKE '%conflict%' OR lower(notes) LIKE '%vs %' OR lower(notes) LIKE '%dubious%' "
    "OR lower(notes) LIKE '%wrong%' OR lower(notes) LIKE '%duplicate%' OR lower(notes) LIKE '%mismatch%' "
    "OR lower(notes) LIKE '%unverified%' OR lower(notes) LIKE '%needs verif%'"
)
_SEV = "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END"


def _collect(con):
    conflicts = [
        {"name": r["person_name"] or "", "note": r["notes"] or "",
         "src": r["source_site"] or "", "facts": (r["claimed_facts"] or "")[:200]}
        for r in con.execute(
            f"SELECT person_name, notes, source_site, claimed_facts FROM web_research_finding "
            f"WHERE {CONFLICT_FILTER} ORDER BY person_name")
    ]
    dupes = [
        {"a": r["left_name"] or "", "b": r["right_name"] or "",
         "ab": r["left_birth_date"] or "", "bb": r["right_birth_date"] or "",
         "score": r["score"], "reason": r["reason"] or ""}
        for r in con.execute(
            "SELECT left_name, right_name, left_birth_date, right_birth_date, score, reason "
            "FROM duplicate_candidates ORDER BY score DESC")
    ]
    issues = [
        {"name": r["person_name"] or "", "type": r["issue_type"], "sev": r["severity"] or "",
         "desc": r["description"] or ""}
        for r in con.execute(
            f"SELECT person_name, issue_type, severity, description FROM validation_issue ORDER BY {_SEV}, person_name")
    ]
    return conflicts, dupes, issues


def build(db_path=WORKING_DB) -> dict:
    with connect(db_path) as con:
        conflicts, dupes, issues = _collect(con)
    html_doc = (_TEMPLATE
                .replace("__CONFLICTS__", json.dumps(conflicts, ensure_ascii=False).replace("</", "<\\/"))
                .replace("__DUPES__", json.dumps(dupes, ensure_ascii=False).replace("</", "<\\/"))
                .replace("__ISSUES__", json.dumps(issues, ensure_ascii=False).replace("</", "<\\/"))
                .replace("__NC__", str(len(conflicts))).replace("__ND__", str(len(dupes))).replace("__NI__", str(len(issues))))
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"conflicts": len(conflicts), "duplicates": len(dupes), "issues": len(issues), "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree · Review</title>
<style>
  :root{--bg:#f4efe7;--ink:#3a2f25;--accent:#7a5c3e;--line:#e3dac9;--card:#fff;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;}
  header{padding:16px 18px 8px;}
  header a.home{color:var(--accent);text-decoration:none;font-size:14px;}
  header h1{font-size:22px;margin:4px 0 2px;}
  header p{color:#8a7866;margin:0;font-size:13px;}
  .tabs{display:flex;gap:6px;flex-wrap:wrap;padding:10px 18px 0;}
  .tabs button{font:inherit;font-size:14px;padding:8px 14px;border:1px solid var(--line);background:#fff;border-radius:8px 8px 0 0;cursor:pointer;}
  .tabs button.on{background:var(--accent);color:#fff;border-color:var(--accent);}
  #q{margin:10px 18px;padding:8px 10px;border:1px solid var(--line);border-radius:7px;width:calc(100% - 36px);max-width:520px;font-size:14px;}
  main{padding:0 18px 60px;}
  .row{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:10px 13px;margin:7px 0;}
  .row .who{font-weight:600;}
  .row .meta{color:#8a7866;font-size:13px;}
  .pill{display:inline-block;font-size:11px;padding:1px 7px;border-radius:10px;margin-right:5px;}
  .sev-critical,.sev-high{background:#f3d9d2;color:#9a3a22;}
  .sev-medium{background:#f3ecd2;color:#7a5a22;}
  .sev-low{background:#e6efe0;color:#3f6b3a;}
  .score{background:#efe6d8;color:#6b513a;}
  .vs{color:#a06b3a;font-style:italic;}
  .count{color:#8a7866;font-size:13px;margin:8px 0;}
</style>
</head>
<body>
<header>
  <a class="home" href="index.html">‹ Home</a>
  <h1>Review &amp; Tree Corrections</h1>
  <p>Issues to check and fix in the master tree — research conflicts, possible duplicates, and date problems. Nothing here changes data automatically.</p>
</header>
<div class="tabs" id="tabs">
  <button data-t="conflicts" class="on">Research conflicts (__NC__)</button>
  <button data-t="dupes">Possible duplicates (__ND__)</button>
  <button data-t="issues">Date/relationship issues (__NI__)</button>
</div>
<input id="q" type="search" placeholder="Filter by name…" autocomplete="off">
<div class="count" id="count" style="padding:0 18px"></div>
<main id="list"></main>
<script>
const DATA={conflicts:__CONFLICTS__,dupes:__DUPES__,issues:__ISSUES__};
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let tab='conflicts',q='';
function rowHTML(t,d){
  if(t==='conflicts') return `<div class="row"><div class="who">${esc(d.name)}</div><div class="meta vs">${esc(d.note)}</div><div class="meta">${esc(d.facts)} ${d.src?'· '+esc(d.src):''}</div></div>`;
  if(t==='dupes') return `<div class="row"><span class="pill score">score ${d.score}</span><span class="who">${esc(d.a)}</span> <span class="vs">↔</span> <span class="who">${esc(d.b)}</span><div class="meta">${esc(d.ab)} / ${esc(d.bb)} — ${esc(d.reason)}</div></div>`;
  return `<div class="row"><span class="pill sev-${esc(d.sev)}">${esc(d.sev)}</span><span class="who">${esc(d.name)}</span> <span class="meta">${esc(d.type)}</span><div class="meta">${esc(d.desc)}</div></div>`;
}
function render(){
  let arr=DATA[tab];
  if(q) arr=arr.filter(d=>JSON.stringify(d).toLowerCase().includes(q));
  document.getElementById('count').textContent=arr.length+' shown';
  document.getElementById('list').innerHTML=arr.slice(0,800).map(d=>rowHTML(tab,d)).join('')||'<p style="color:#8a7866">None.</p>';
}
document.getElementById('tabs').addEventListener('click',e=>{const b=e.target.closest('button');if(b){tab=b.dataset.t;[...e.currentTarget.children].forEach(x=>x.classList.toggle('on',x===b));render();}});
document.getElementById('q').addEventListener('input',e=>{q=e.target.value.trim().toLowerCase();render();});
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
