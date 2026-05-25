"""Build ``gallery.html`` — every photo and document on the site, in one place.

Shows all catalogued media (including the ~448 not yet linked to a specific
person), as a lazy-loaded thumbnail grid with a Photos/Documents/All toggle and
a search box (by linked person, caption, or filename). Clicking a thumbnail
opens the full image. Names of living people are shown as "Living".

    python -m src.build_gallery
"""

from __future__ import annotations

import json
from collections import defaultdict
from urllib.parse import quote

from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import LIVING_NAME, is_living

OUT_PATH = EXPORTS_DIR / "gallery.html"


def _collect(con, media_base: str) -> list[dict]:
    def href(name, path):
        if media_base:
            return media_base + quote(name)
        import os
        return "/".join(os.path.relpath(path, EXPORTS_DIR).split(os.sep))

    living = set()
    for r in con.execute("SELECT person_id, birth_date, death_date, generation FROM people"):
        if is_living(r["birth_date"], r["death_date"], r["generation"]):
            living.add(r["person_id"])

    people = defaultdict(list)
    for r in con.execute(
        "SELECT media_id, person_id, person_name FROM media_person_link WHERE link_type!='review_false_match'"
    ):
        nm = LIVING_NAME if r["person_id"] in living else (r["person_name"] or "")
        if nm:
            people[r["media_id"]].append(nm)

    items = []
    for r in con.execute(
        "SELECT media_id, file_name, file_path, kind, caption FROM media_object ORDER BY kind, file_name"
    ):
        ppl = sorted(set(people.get(r["media_id"], [])))
        items.append({
            "src": href(r["file_name"], r["file_path"]),
            "kind": r["kind"] or "photo",
            "cap": r["caption"] or "",
            "ppl": ppl,
            "q": (" ".join(ppl) + " " + (r["caption"] or "") + " " + r["file_name"]).lower(),
        })
    return items


def build(db_path=WORKING_DB, media_base: str = "") -> dict:
    with connect(db_path) as con:
        items = _collect(con, media_base)
    photos = sum(1 for i in items if i["kind"] == "photo")
    data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    html_doc = _TEMPLATE.replace("__DATA__", data).replace("__PHOTOS__", str(photos)).replace("__DOCS__", str(len(items) - photos))
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"items": len(items), "photos": photos, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree · Photo Gallery</title>
<style>
  :root{--bg:#f4efe7;--ink:#3a2f25;--accent:#7a5c3e;--line:#e3dac9;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;}
  header{position:sticky;top:0;z-index:5;background:rgba(244,239,231,.96);border-bottom:1px solid var(--line);
    padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;backdrop-filter:blur(4px);}
  header a.home{color:var(--accent);text-decoration:none;font-size:14px;}
  header h1{font-size:17px;margin:0;}
  header input{flex:1;min-width:160px;padding:7px 10px;border:1px solid var(--line);border-radius:7px;font-size:14px;}
  .seg button{font:inherit;font-size:13px;padding:6px 12px;border:1px solid var(--line);background:#fff;cursor:pointer;}
  .seg button:first-child{border-radius:7px 0 0 7px;} .seg button:last-child{border-radius:0 7px 7px 0;}
  .seg button.on{background:var(--accent);color:#fff;border-color:var(--accent);}
  .count{color:#8a7866;font-size:12.5px;}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;padding:14px;}
  figure{margin:0;background:#fff;border:1px solid var(--line);border-radius:9px;overflow:hidden;}
  figure a{display:block;}
  figure img{width:100%;height:150px;object-fit:contain;display:block;background:#e7ddc9;}
  figcaption{padding:6px 8px;font-size:12px;color:#5b4a35;}
  figcaption .ppl{color:var(--accent);}
  @media (max-width:600px){.grid{grid-template-columns:repeat(auto-fill,minmax(108px,1fr));} figure img{height:108px;}}
  #lb{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;align-items:center;justify-content:center;z-index:9999;}
  #lb.open{display:flex;}
  #lb img{max-width:96vw;max-height:88vh;object-fit:contain;border-radius:4px;}
  #lbx{position:fixed;top:10px;right:16px;color:#fff;font-size:40px;line-height:1;cursor:pointer;z-index:10000;}
  #lbcap{position:fixed;bottom:14px;left:0;right:0;text-align:center;color:#eee;font-size:13px;padding:0 16px;}
</style>
</head>
<body>
<header>
  <a class="home" href="index.html">‹ Home</a>
  <h1>Photo Gallery</h1>
  <div class="seg" id="seg">
    <button data-k="photo" class="on">Photos (__PHOTOS__)</button>
    <button data-k="document">Documents (__DOCS__)</button>
    <button data-k="all">All</button>
  </div>
  <input id="q" type="search" placeholder="Search by person, caption, filename…" autocomplete="off">
  <span class="count" id="count"></span>
</header>
<div class="grid" id="grid"></div>
<div id="lb"><span id="lbx">×</span><img id="lbimg" alt=""><div id="lbcap"></div></div>
<script>
const ITEMS=__DATA__;
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let kind='photo', q='';
function render(){
  const list=ITEMS.filter(i=>(kind==='all'||i.kind===kind)&&(!q||i.q.includes(q)));
  document.getElementById('count').textContent=list.length+' shown';
  document.getElementById('grid').innerHTML=list.slice(0,1500).map(i=>{
    const cap=i.ppl.length?`<span class="ppl">${esc(i.ppl.slice(0,3).join(', '))}${i.ppl.length>3?' +'+(i.ppl.length-3):''}</span>`:(i.cap?esc(i.cap):'<span style="color:#b3a487">unidentified</span>');
    return `<figure><a href="${esc(i.src)}" class="lb"><img loading="lazy" src="${esc(i.src)}" alt="" onerror="this.style.opacity=.25"></a><figcaption>${cap}</figcaption></figure>`;
  }).join('');
}
document.getElementById('seg').addEventListener('click',e=>{const b=e.target.closest('button');if(b){kind=b.dataset.k;
  [...e.currentTarget.children].forEach(x=>x.classList.toggle('on',x===b));render();}});
document.getElementById('q').addEventListener('input',e=>{q=e.target.value.trim().toLowerCase();render();});
const lb=document.getElementById('lb'),lbimg=document.getElementById('lbimg'),lbcap=document.getElementById('lbcap');
document.getElementById('grid').addEventListener('click',e=>{
  const a=e.target.closest('a.lb'); if(!a) return; e.preventDefault();
  lbimg.src=a.getAttribute('href'); const fc=a.parentNode.querySelector('figcaption');
  lbcap.textContent=fc?fc.textContent:''; lb.classList.add('open');
});
function closeLB(){lb.classList.remove('open');lbimg.removeAttribute('src');}
lb.addEventListener('click',e=>{if(e.target.id!=='lbimg')closeLB();});
addEventListener('keydown',e=>{if(e.key==='Escape')closeLB();});
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
