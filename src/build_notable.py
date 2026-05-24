"""Build ``notable.html`` — a curated showcase of the most notable ancestors.

Pulls the ``notable_person_candidate`` rows and groups them into sections:
Mayflower passengers, military service, colonial figures, and the (clearly
flagged, unverified) royal/noble and medieval claims. Each person is a card with
their dates, place, the reason they're notable, and a side badge; the genuinely
famous figures get their verified portrait (reused from the storybook).

A quick, high-signal entry point versus paging the full storybook.

    python -m src.build_notable
"""

from __future__ import annotations

import json
from collections import defaultdict

from .ancestral_sides import compute_sides
from .build_storybook import noble_images
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB

OUT_PATH = EXPORTS_DIR / "notable.html"

# category key -> (display title, sort priority, flagged-as-unverified)
SECTIONS = [
    ("mayflower", "⚓ Mayflower Passengers", False),
    ("military_title", "⚔ Military Service", False),
    ("colonial_public_figure", "🏛 Colonial Figures", False),
    ("royal_noble", "👑 Royal & Noble Claims", True),
    ("medieval_descent", "🏰 Medieval Lines", True),
]
PRIORITY = {k: i for i, (k, _, _) in enumerate(SECTIONS)}


def _collect(con) -> list[dict]:
    sides, _, _ = compute_sides(con)
    ni_map = noble_images()
    people: dict[str, dict] = {}
    for r in con.execute(
        "SELECT person_id, person_name, generation, birth_date, death_date, birth_place, "
        "death_place, category, notable_reason FROM notable_person_candidate"
    ):
        pid = r["person_id"]
        e = people.setdefault(pid, {
            "name": r["person_name"] or "(unknown)", "gen": r["generation"],
            "born": r["birth_date"] or "", "died": r["death_date"] or "",
            "place": r["birth_place"] or r["death_place"] or "",
            "cats": set(), "reasons": set(), "side": sides.get(pid, []),
            "ni": ni_map.get(pid),
        })
        if r["category"]:
            e["cats"].add(r["category"])
        if r["notable_reason"]:
            e["reasons"].add(r["notable_reason"])
    out = []
    for e in people.values():
        cats = [c for c in e["cats"] if c in PRIORITY]
        if not cats:
            continue
        e["cat"] = min(cats, key=lambda c: PRIORITY[c])  # primary section
        e["reasons"] = sorted(e["reasons"])
        e.pop("cats")
        out.append(e)
    out.sort(key=lambda x: (PRIORITY[x["cat"]], x["gen"] if x["gen"] is not None else 99, x["name"]))
    return out


def build(db_path=WORKING_DB) -> dict:
    with connect(db_path) as con:
        people = _collect(con)
        _, side_labels, side_keys = compute_sides(con)
    counts = {k: sum(1 for p in people if p["cat"] == k) for k, _, _ in SECTIONS}
    html_doc = (
        _TEMPLATE.replace("__DATA__", json.dumps(people, ensure_ascii=False).replace("</", "<\\/"))
        .replace("__SECTIONS__", json.dumps([[k, t, f] for k, t, f in SECTIONS]))
        .replace("__SIDELABELS__", json.dumps(side_labels))
        .replace("__SIDEKEYS__", json.dumps(side_keys))
        .replace("__TOTAL__", str(len(people)))
    )
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"notable": len(people), "by_section": counts, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree · Notable Ancestors</title>
<style>
  :root { --bg:#f4efe7; --ink:#3a2f25; --accent:#7a5c3e; --card:#fff; --line:#e3dac9; }
  * { box-sizing:border-box; }
  body { margin:0; background:radial-gradient(circle at 50% -5%,#fbf7f0,var(--bg)); color:var(--ink);
    font:16px/1.6 Georgia,"Times New Roman",serif; min-height:100vh; }
  header { text-align:center; padding:30px 20px 6px; }
  header a.home { position:absolute; top:16px; left:18px; color:var(--accent); text-decoration:none; font-size:14px; }
  header h1 { font-size:32px; margin:0; }
  header p { color:#8a7866; margin:6px 0 0; }
  #sides { display:flex; gap:8px; justify-content:center; margin:16px 0 6px; flex-wrap:wrap; }
  #sides button { font:inherit; font-size:14px; padding:7px 18px; border-radius:22px; cursor:pointer;
    border:1px solid var(--line); background:#fff; color:var(--ink); }
  #sides button.on { background:var(--accent); color:#fff; border-color:var(--accent); }
  main { max-width:1000px; margin:0 auto; padding:10px 18px 60px; }
  h2.sec { font-size:22px; border-bottom:2px solid var(--accent); padding-bottom:5px; margin:30px 0 4px; }
  h2.sec .n { font-size:14px; color:#8a7866; font-weight:normal; }
  .flag { font-size:13px; font-style:italic; color:#a06b3a; margin:2px 0 10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden;
    display:flex; flex-direction:column; }
  .card img { width:100%; height:180px; object-fit:cover; }
  .card .body { padding:12px 14px; }
  .card h3 { margin:0 0 3px; font-size:17px; }
  .card .meta { color:#8a7866; font-size:12.5px; margin-bottom:6px; }
  .card .reason { font-size:13.5px; }
  .badge { display:inline-block; font-size:11px; padding:1px 7px; border-radius:10px; background:#efe6d8; color:#6b513a; margin-right:4px; }
  footer { text-align:center; color:#a3937f; font-size:13px; padding-bottom:24px; }
  @media (max-width:600px){ header h1{font-size:26px} .grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))} }
</style>
</head>
<body>
<header>
  <a class="home" href="index.html">‹ Home</a>
  <h1>Notable Ancestors</h1>
  <p>__TOTAL__ standout figures across the tree</p>
  <div id="sides"></div>
</header>
<main id="main"></main>
<footer>troytree.org · royal/noble & medieval claims are family lore, unproven through the colonial bridge</footer>
<script>
const PEOPLE=__DATA__, SECTIONS=__SECTIONS__, SIDE_LABELS=__SIDELABELS__, SIDE_KEYS=__SIDEKEYS__;
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let side=new URLSearchParams(location.search).get('side')||''; if(!SIDE_KEYS.includes(side)) side='';

function card(p){
  const dates=[p.born,p.died].filter(Boolean).join(' – ');
  const sideb=(p.side||[]).map(s=>`<span class="badge">${esc(SIDE_LABELS[s]||s)}</span>`).join('');
  const img=p.ni?`<img src="${esc(p.ni.portrait)}" alt="" onerror="this.style.display='none'">`:'';
  return `<div class="card">${img}<div class="body"><h3>${esc(p.name)}</h3>`
    +`<div class="meta">${p.gen==null?'':'Gen '+p.gen} ${sideb}</div>`
    +(dates?`<div class="meta">${esc(dates)}</div>`:'')
    +(p.place?`<div class="meta">📍 ${esc(p.place)}</div>`:'')
    +`<div class="reason">${esc(p.reasons.join('; '))}</div></div></div>`;
}
function render(){
  const main=document.getElementById('main'); let h='';
  for(const [key,title,flagged] of SECTIONS){
    let list=PEOPLE.filter(p=>p.cat===key && (!side || (p.side&&p.side.includes(side))));
    if(!list.length) continue;
    h+=`<h2 class="sec">${esc(title)} <span class="n">${list.length}</span></h2>`;
    if(flagged) h+=`<div class="flag">⚠ Family legend — unproven through the colonial bridge; treat as lore, not established fact.</div>`;
    h+=`<div class="grid">`+list.map(card).join('')+`</div>`;
  }
  main.innerHTML=h||'<p style="text-align:center;color:#8a7866">No notable ancestors on this side.</p>';
}
const sidesEl=document.getElementById('sides');
function paint(){ sidesEl.innerHTML=[['','Both']].concat(SIDE_KEYS.map(k=>[k,SIDE_LABELS[k]]))
  .map(([v,l])=>`<button data-v="${v}" class="${v===side?'on':''}">${esc(l)}</button>`).join(''); }
sidesEl.addEventListener('click',e=>{const b=e.target.closest('button'); if(b){side=b.dataset.v; paint(); render();}});
paint(); render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
