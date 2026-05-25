"""Build ``castles.html`` — the ancestral castles, as they stand today.

A gallery of the castles, halls, and great houses tied to our (claimed) noble
ancestors, each shown with a MODERN photograph, its current status (still
standing, ruins, rebuilt), a line on what it is today, and the family members
connected to it. Data is curated in ``data/exports/castles.json``.

    python -m src.build_castles
"""

from __future__ import annotations

import json

from .paths import EXPORTS_DIR, WORKING_DB

OUT_PATH = EXPORTS_DIR / "castles.html"
CASTLES_JSON = EXPORTS_DIR / "castles.json"
_STATUS_ORDER = {"Still stands": 0, "Rebuilt": 1, "Survives as ruins": 2, "Largely gone": 3}


def build(db_path=WORKING_DB) -> dict:
    castles = []
    if CASTLES_JSON.exists():
        try:
            castles = json.loads(CASTLES_JSON.read_text(encoding="utf-8"))
        except Exception:
            castles = []
    castles = [c for c in castles if c.get("photo")]
    castles.sort(key=lambda c: (_STATUS_ORDER.get(c.get("status", ""), 9), c.get("name", "")))
    standing = sum(1 for c in castles if c.get("status") == "Still stands")
    story_ids = []
    sp = EXPORTS_DIR / "story_ids.json"
    if sp.exists():
        try:
            story_ids = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            story_ids = []
    html_doc = (_TEMPLATE
                .replace("__DATA__", json.dumps(castles, ensure_ascii=False).replace("</", "<\\/"))
                .replace("__STORYIDS__", json.dumps(story_ids))
                .replace("__COUNT__", str(len(castles)))
                .replace("__STANDING__", str(standing)))
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"castles": len(castles), "still_standing": standing, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree · Ancestral Castles</title>
<style>
  :root { --bg:#f4efe7; --ink:#3a2f25; --accent:#7a5c3e; --card:#fff; --line:#e3dac9; }
  * { box-sizing:border-box; }
  body { margin:0; background:radial-gradient(circle at 50% -5%,#fbf7f0,var(--bg)); color:var(--ink);
    font:16px/1.6 Georgia,"Times New Roman",serif; min-height:100vh; }
  header { text-align:center; padding:30px 20px 6px; position:relative; }
  header a.home { position:absolute; top:16px; left:18px; color:var(--accent); text-decoration:none; font-size:14px; font-family:-apple-system,Segoe UI,sans-serif; }
  header h1 { font-size:32px; margin:0; }
  header p { color:#8a7866; margin:6px 0 0; font-size:15px; }
  header .flag { font-style:italic; color:#a06b3a; font-size:13.5px; margin-top:8px; }
  main { max-width:1080px; margin:0 auto; padding:18px 18px 70px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(290px,1fr)); gap:18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden;
    display:flex; flex-direction:column; box-shadow:0 2px 10px rgba(90,70,50,.06); }
  .card .ph { position:relative; cursor:zoom-in; }
  .card img { width:100%; height:210px; object-fit:contain; display:block; background:#e7ddc9; }
  .card .badge { position:absolute; top:10px; right:10px; font-size:11.5px; font-family:-apple-system,Segoe UI,sans-serif;
    padding:3px 9px; border-radius:14px; color:#fff; backdrop-filter:blur(2px); }
  .s-stands { background:rgba(70,120,70,.92); }
  .s-ruins { background:rgba(176,112,40,.92); }
  .s-rebuilt { background:rgba(70,100,150,.92); }
  .s-gone { background:rgba(110,100,90,.92); }
  .card .body { padding:14px 16px 16px; flex:1; display:flex; flex-direction:column; }
  .card h2 { font-size:20px; margin:0 0 4px; }
  .card .today { font-size:14px; color:#5b4a35; margin:0 0 10px; }
  .card .ppl { font-size:12.5px; font-family:-apple-system,Segoe UI,sans-serif; margin-top:auto; padding-top:9px; }
  .card .ppl .lbl2 { color:#8a7866; font-size:10.5px; text-transform:uppercase; letter-spacing:.6px; margin-bottom:4px; }
  .card .ppl ul { list-style:none; margin:0; padding:0; }
  .card .ppl li { margin:2px 0; color:#4f4030; line-height:1.4; }
  .card .ppl li .nm { color:var(--accent); font-weight:600; }
  .card .ppl li a.nm { text-decoration:none; } .card .ppl li a.nm:hover { text-decoration:underline; }
  .card .ppl li .sd { color:#9a8a76; }
  .card .ppl li.more { color:#9a8a76; font-style:italic; }
  .card .cr { font-size:10.5px; color:#a4937e; margin-top:8px; }
  .card .cr a { color:#a4937e; }
  footer { text-align:center; color:#a3937f; font-size:13px; padding:0 0 24px; }
  @media (max-width:600px){ header h1{font-size:25px} .grid{grid-template-columns:1fr} .card img{height:200px} }
  #lb{position:fixed;inset:0;background:rgba(0,0,0,.93);display:none;align-items:center;justify-content:center;z-index:9999;flex-direction:column;}
  #lb.open{display:flex;}
  #lb img{max-width:96vw;max-height:84vh;object-fit:contain;border-radius:4px;}
  #lbcap{color:#eee;font-size:14px;margin-top:12px;text-align:center;padding:0 16px;font-family:-apple-system,Segoe UI,sans-serif;}
  #lbx{position:fixed;top:10px;right:16px;color:#fff;font-size:40px;line-height:1;cursor:pointer;}
</style>
</head>
<body>
<header>
  <a class="home" href="index.html">‹ Home</a>
  <h1>🏰 Ancestral Castles</h1>
  <p>The great houses and castles of our claimed noble ancestors — photographed as they stand today. <b>__STANDING__</b> of <b>__COUNT__</b> still stand.</p>
  <p class="flag">⚠ These noble lines are family legend — unproven through the colonial bridge. The castles are real; the descent is the part still to be proven.</p>
</header>
<main><div class="grid" id="grid"></div></main>
<footer>troytree.org · private family archive · castle photographs courtesy of Wikimedia Commons</footer>
<div id="lb"><span id="lbx">×</span><img id="lbimg" alt=""><div id="lbcap"></div></div>
<script>
const CASTLES=__DATA__;
const STORY_IDS=new Set(__STORYIDS__);
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const cls={'Still stands':'s-stands','Survives as ruins':'s-ruins','Rebuilt':'s-rebuilt','Largely gone':'s-gone'};
function card(c){
  const all=(c.people||[]);
  const ppl=all.slice(0,5).map(p=>{
    const nm = (p.pid && STORY_IDS.has(p.pid))
      ? `<a class="nm" href="story.html#${encodeURIComponent(p.pid)}">${esc(p.name)} ›</a>`
      : `<span class="nm">${esc(p.name)}</span>`;
    return `<li>${nm}${p.rel?` — ${esc(p.rel)}`:''}${p.side?` <span class="sd">· ${esc(p.side)} side</span>`:''}</li>`;
  }).join('');
  const more=all.length>5?`<li class="more">+${all.length-5} more</li>`:'';
  return `<div class="card"><div class="ph" data-full="${esc(c.photo)}" data-cap="${esc(c.name+' — '+(c.caption||''))}">`
    +`<img loading="lazy" src="${esc(c.photo)}" alt="${esc(c.name)}" onerror="this.closest('.card').style.display='none'">`
    +(c.status?`<span class="badge ${cls[c.status]||'s-gone'}">${esc(c.status)}</span>`:'')+`</div>`
    +`<div class="body"><h2>${esc(c.name)}</h2>`
    +(c.today?`<p class="today">${esc(c.today)}</p>`:'')
    +(ppl?`<div class="ppl"><div class="lbl2">Your ancestors who lived here</div><ul>${ppl}${more}</ul></div>`:'')
    +(c.credit?`<div class="cr">📷 ${c.commons?`<a href="${esc(c.commons)}" target="_blank">${esc(c.credit)}</a>`:esc(c.credit)}</div>`:'')
    +`</div></div>`;
}
document.getElementById('grid').innerHTML=CASTLES.map(card).join('')||'<p style="color:#8a7866;text-align:center">No castle photos yet.</p>';
const lb=document.getElementById('lb'),lbimg=document.getElementById('lbimg'),lbcap=document.getElementById('lbcap');
document.getElementById('grid').addEventListener('click',e=>{const ph=e.target.closest('.ph'); if(!ph) return;
  lbimg.src=ph.dataset.full; lbcap.textContent=ph.dataset.cap; lb.classList.add('open');});
function closeLB(){lb.classList.remove('open');lbimg.removeAttribute('src');}
lb.addEventListener('click',e=>{if(e.target.id!=='lbimg')closeLB();});
addEventListener('keydown',e=>{if(e.key==='Escape')closeLB();});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
