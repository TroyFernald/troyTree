"""Build ``graph_3d.html`` — the whole tree as one interactive 3D force-directed
cloud.

Nodes are people (colored by generation, sized by how connected they are);
links are parent and spouse relationships, de-duplicated from the bidirectional
rows in ``family_relationships``. Rendering uses the vendored ``3d-force-graph``
UMD bundle in ``data/exports/lib/`` (three.js included), so the page works
offline from a Drive mirror and unchanged on a website.

Interaction: scroll to zoom, drag to rotate/pan, hover for a name, click a
person to fly the camera to them, and a search box to jump to anyone.

    python -m src.build_graph_3d
"""

from __future__ import annotations

import json
from collections import defaultdict

from .ancestral_sides import compute_sides
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import LIVING_NAME, is_living

OUT_PATH = EXPORTS_DIR / "graph_3d.html"


def _collect(con, redact_living: bool = True) -> tuple[list[dict], list[dict]]:
    people = {}
    for r in con.execute(
        "SELECT person_id, full_name, generation, relationship_to_root, birth_date, birth_place, death_date FROM people"
    ):
        living = redact_living and is_living(r["birth_date"], r["death_date"], r["generation"])
        name = LIVING_NAME if living else (r["full_name"] or "(unknown)")
        people[r["person_id"]] = {
            "id": r["person_id"], "name": name,
            "gen": r["generation"], "rel": r["relationship_to_root"] or "",
            "b": "" if living else (r["birth_date"] or ""),
            "bp": "" if living else (r["birth_place"] or ""),
            "d": "" if living else (r["death_date"] or ""),
        }

    seen: set = set()
    links: list[dict] = []
    degree: dict[str, int] = defaultdict(int)

    def add(a: str, b: str, kind: str) -> None:
        if a not in people or b not in people or a == b:
            return
        key = (kind, a, b) if kind == "parent" else (kind, *sorted((a, b)))
        if key in seen:
            return
        seen.add(key)
        links.append({"source": a, "target": b, "kind": kind})
        degree[a] += 1
        degree[b] += 1

    for r in con.execute(
        "SELECT person_id, related_person_id, relationship_type FROM family_relationships "
        "WHERE relationship_type IN ('parent', 'spouse')"
    ):
        add(r["person_id"], r["related_person_id"], r["relationship_type"])

    nodes = []
    for pid, n in people.items():
        n["val"] = 1 + degree.get(pid, 0)
        nodes.append(n)
    return nodes, links


def build(db_path=WORKING_DB, redact_living: bool = True) -> dict:
    with connect(db_path) as con:
        nodes, links = _collect(con, redact_living)
        sides, side_labels, side_keys = compute_sides(con)
    for n in nodes:
        n["side"] = sides.get(n["id"], [])
    data = json.dumps({"nodes": nodes, "links": links}, ensure_ascii=False).replace("</", "<\\/")
    gens = sorted({n["gen"] for n in nodes if n["gen"] is not None})
    max_gen = max(gens) if gens else 0
    html_doc = (
        _TEMPLATE.replace("__DATA__", data)
        .replace("__NODES__", str(len(nodes)))
        .replace("__LINKS__", str(len(links)))
        .replace("__MAXGEN__", str(max_gen))
        .replace("__SIDELABELS__", json.dumps(side_labels))
        .replace("__SIDEKEYS__", json.dumps(side_keys))
    )
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"nodes": len(nodes), "links": len(links), "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree · 3D connections</title>
<style>
  html,body { margin:0; height:100%; background:#0b0e14; color:#e8e8e8; overflow:hidden;
    font:14px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  #graph { width:100vw; height:100vh; }
  #panel { position:fixed; top:12px; left:12px; z-index:10; background:rgba(16,20,28,.82);
    border:1px solid #2a3340; border-radius:9px; padding:12px 14px; max-width:300px; backdrop-filter:blur(4px); }
  #panel h1 { font-size:16px; margin:0 0 4px; }
  #panel .meta { color:#8b97a7; font-size:12px; margin-bottom:9px; }
  #panel input { width:100%; padding:7px 9px; border:1px solid #2a3340; border-radius:6px;
    background:#0d1119; color:#e8e8e8; font-size:13px; }
  #results { margin-top:6px; max-height:230px; overflow:auto; }
  #results div { padding:5px 7px; border-radius:5px; cursor:pointer; font-size:13px; }
  #results div:hover { background:#1b2330; }
  #sides { display:flex; gap:5px; margin:9px 0 3px; }
  #sides button { flex:1; background:#1b2330; color:#cdd6e2; border:1px solid #2a3340;
    border-radius:6px; padding:5px 4px; font-size:11.5px; cursor:pointer; }
  #sides button.on { background:#33415a; color:#fff; border-color:#46597a; }
  #legend { position:fixed; bottom:12px; left:12px; z-index:10; background:rgba(16,20,28,.82);
    border:1px solid #2a3340; border-radius:9px; padding:9px 12px; font-size:12px; color:#aab4c2; }
  #legend .bar { height:9px; width:180px; border-radius:5px; margin:5px 0 3px;
    background:linear-gradient(90deg,hsl(205,80%,62%),hsl(285,70%,62%),hsl(20,85%,60%)); }
  #legend .ends { display:flex; justify-content:space-between; }
  #hint { position:fixed; bottom:12px; right:12px; z-index:10; color:#8b97a7; font-size:12px; text-align:right; line-height:1.6; }
  #hint b { color:#c2ccd8; }
  #help { position:fixed; inset:0; z-index:30; display:flex; align-items:center; justify-content:center; background:rgba(5,7,11,.62); }
  #help.hide { display:none; }
  #help .box { background:rgba(16,20,28,.98); border:1px solid #2a3340; border-radius:12px; padding:20px 24px; max-width:340px; box-shadow:0 12px 40px rgba(0,0,0,.6); }
  #help h2 { margin:0 0 6px; font-size:18px; }
  #help ul { margin:8px 0 16px; padding-left:18px; color:#c2ccd8; font-size:13.5px; line-height:1.7; }
  #help b { color:#fff; }
  #help button { background:#33415a; color:#fff; border:0; border-radius:7px; padding:10px 18px; font-size:14px; cursor:pointer; width:100%; }
  #help button:hover { background:#46597a; }
  #info { position:fixed; top:12px; right:12px; z-index:15; width:262px; max-width:82vw;
    background:rgba(16,20,28,.93); border:1px solid #2a3340; border-radius:9px; padding:12px 14px;
    color:#e8e8e8; font-size:13px; display:none; backdrop-filter:blur(4px); }
  #info h2 { font-size:16px; margin:0 14px 2px 0; }
  #info .sub { color:#8b97a7; font-size:12px; margin-bottom:6px; }
  #info .fact { font-size:12.5px; color:#c2ccd8; margin:2px 0; }
  #info .rel { margin-top:6px; font-size:12.5px; }
  #info .rel b { color:#8b97a7; }
  #info .lk { color:#7fb0ff; cursor:pointer; }
  #info .lk:hover { text-decoration:underline; }
  #infoX { position:absolute; top:5px; right:9px; background:none; border:0; color:#8b97a7; font-size:19px; cursor:pointer; }
  @media (max-width:600px){ #info{ top:auto; bottom:46px; left:8px; right:8px; width:auto; max-width:none } #panel{ max-width:62vw } }
</style>
</head>
<body>
<div id="panel">
  <a href="index.html" style="color:#8b97a7;text-decoration:none;font-size:12px">‹ Home</a>
  <h1>Family connections</h1>
  <div class="meta">__NODES__ people · __LINKS__ links · click anyone to fly to them</div>
  <div id="sides"></div>
  <input id="q" type="search" placeholder="Find a person…" autocomplete="off">
  <div id="results"></div>
</div>
<div id="legend">Generation
  <div class="bar"></div>
  <div class="ends"><span>0 (you)</span><span>__MAXGEN__</span></div>
</div>
<div id="hint"><b>Drag</b> to rotate · <b>scroll / pinch</b> to zoom · <b>right-drag</b> to slide<br><b>Click a person</b> to fly to them</div>
<div id="info"></div>
<div id="help"><div class="box">
  <h2>🪐 Flying through the family</h2>
  <ul>
    <li><b>Drag</b> to rotate the whole cloud around</li>
    <li><b>Scroll</b> or pinch to zoom in and out</li>
    <li><b>Right-drag</b> (or two-finger drag) to slide sideways</li>
    <li><b>Click any person</b> to fly the camera to them and light up their connections</li>
    <li><b>Search</b> a name (top-left) to jump straight to anyone</li>
    <li>Click empty space to fly back out</li>
  </ul>
  <button id="helpGo">Start exploring →</button>
</div></div>
<div id="graph"></div>
<script src="./lib/3d-force-graph.min.js"></script>
<script>
const DATA = __DATA__;
const MAXGEN = Math.max(1, __MAXGEN__);
const SIDE_LABELS = __SIDELABELS__, SIDE_KEYS = __SIDEKEYS__;
let CUR = DATA;
const hl = new Set();
const lid = l => typeof l.source==='object' ? l.source.id : l.source;
const tid = l => typeof l.target==='object' ? l.target.id : l.target;
const byId = {}; DATA.nodes.forEach(n => byId[n.id] = n);
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const colorFor = g => g==null ? '#6b7686'
  : `hsl(${205 + (g/MAXGEN)*175}, 75%, 60%)`;   // gen 0 blue -> deep gens warm

const elem = document.getElementById('graph');
const Graph = ForceGraph3D()(elem)
  .graphData(DATA)
  .backgroundColor('#0b0e14')
  .controlType('orbit')          // stable "up" — easier to fly around than free-tumbling trackball
  .nodeLabel(n => `${n.name}${n.gen==null?'':' · gen '+n.gen}`)
  .nodeColor(n => colorFor(n.gen))
  .nodeVal(n => n.val)
  .nodeRelSize(2.2)
  .nodeOpacity(0.92)
  .linkColor(l => hl.has(l) ? '#ffd24a' : (l.kind==='spouse' ? 'rgba(235,165,95,0.6)' : 'rgba(150,180,228,0.4)'))
  .linkWidth(l => hl.has(l) ? 2.4 : 0.8)
  .warmupTicks(40)
  .cooldownTime(6000)
  .onNodeClick(focusNode)
  .onBackgroundClick(() => { hl.clear(); Graph.linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth()); info.style.display='none'; });

// gentle ambient rotation until the user interacts
let spin = true;
const ctrl = Graph.controls();
ctrl.addEventListener('start', () => spin = false);
let angle = 0;
(function rotate(){
  if (spin) { angle += 0.0015; const d = 1400;
    Graph.cameraPosition({ x: d*Math.sin(angle), z: d*Math.cos(angle) }); }
  requestAnimationFrame(rotate);
})();

function focusNode(node) {
  spin = false;
  hl.clear();
  Graph.graphData().links.forEach(l => { if (lid(l)===node.id || tid(l)===node.id) hl.add(l); });
  Graph.linkColor(Graph.linkColor()).linkWidth(Graph.linkWidth());
  showInfo(node);
  const dist = 120;
  const r = Math.hypot(node.x,node.y,node.z) || 1;
  const ratio = 1 + dist/r;
  Graph.cameraPosition({x:node.x*ratio, y:node.y*ratio, z:node.z*ratio}, node, 1200);
}

const info = document.getElementById('info');
function showInfo(node) {
  const parents=[], children=[], spouses=[];
  Graph.graphData().links.forEach(l => {
    const s=lid(l), t=tid(l); if (s!==node.id && t!==node.id) return;
    if (l.kind==='spouse') spouses.push(s===node.id?t:s);
    else if (s===node.id) children.push(t); else parents.push(s);
  });
  const nm = id => byId[id] ? byId[id].name : id;
  const sec = (label,arr) => arr.length ? `<div class="rel"><b>${label}:</b> ${arr.map(id=>`<span class="lk" data-id="${esc(id)}">${esc(nm(id))}</span>`).join(', ')}</div>` : '';
  const dates = [node.b, node.d].filter(Boolean).join(' – ');
  info.innerHTML = `<button id="infoX">×</button><h2>${esc(node.name)}</h2>`
    + `<div class="sub">${node.gen==null?'':'Generation '+node.gen}${node.rel?' · '+esc(node.rel):''}</div>`
    + (dates?`<div class="fact">📅 ${esc(dates)}</div>`:'')
    + (node.bp?`<div class="fact">📍 ${esc(node.bp)}</div>`:'')
    + sec('Parents',parents) + sec('Spouse',spouses) + sec('Children',children);
  info.style.display = 'block';
}
info.addEventListener('click', e => {
  if (e.target.id==='infoX') { info.style.display='none'; return; }
  const lk = e.target.closest('.lk'); if (lk && byId[lk.dataset.id]) focusNode(byId[lk.dataset.id]);
});

// search
const q = document.getElementById('q'), results = document.getElementById('results');
q.addEventListener('input', () => {
  const v = q.value.trim().toLowerCase();
  if (!v) { results.innerHTML=''; return; }
  const hits = CUR.nodes.filter(n => n.name.toLowerCase().includes(v)).slice(0, 40);
  results.innerHTML = hits.map(n =>
    `<div data-id="${n.id}">${n.name}<span style="color:#6b7686"> ${n.gen==null?'':'· g'+n.gen}</span></div>`).join('');
});
results.addEventListener('click', e => {
  const d = e.target.closest('div'); if (!d) return;
  const node = CUR.nodes.find(n => n.id === d.dataset.id);
  if (node) focusNode(node);
});

// Fernald / Bagley side filter
const sidesEl = document.getElementById('sides');
function applySide(s){
  if (!s) { CUR = DATA; }
  else {
    const ns = DATA.nodes.filter(n => n.gen===0 || (n.side && n.side.includes(s)));
    const ids = new Set(ns.map(n => n.id));
    CUR = { nodes: ns, links: DATA.links.filter(l => ids.has(lid(l)) && ids.has(tid(l))) };
  }
  Graph.graphData(CUR);
  [...sidesEl.children].forEach(b => b.classList.toggle('on', b.dataset.v===s));
}
sidesEl.innerHTML = [['','Both']].concat(SIDE_KEYS.map(k => [k, SIDE_LABELS[k]]))
  .map(([v,l]) => `<button data-v="${v}">${l}</button>`).join('');
sidesEl.addEventListener('click', e => { const b=e.target.closest('button'); if(b) applySide(b.dataset.v); });
const _usp = new URLSearchParams(location.search).get('side');
applySide(SIDE_KEYS.includes(_usp) ? _usp : '');

// one-time "how to navigate" card
document.getElementById('helpGo').addEventListener('click', () => document.getElementById('help').classList.add('hide'));
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
