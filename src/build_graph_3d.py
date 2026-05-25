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
  .ctl { flex:1; background:#1b2330; color:#cdd6e2; border:1px solid #2a3340; border-radius:6px; padding:6px 4px; font-size:12px; cursor:pointer; }
  .ctl.on { background:#2e6b4a; color:#fff; border-color:#3f8a61; }
  #flykeys { position:fixed; bottom:46px; right:12px; z-index:10; display:none; color:#9fb0c2; font-size:12px; text-align:right; line-height:1.6; }
  #labels { position:fixed; inset:0; pointer-events:none; z-index:8; }
  .nlab { position:absolute; transform:translate(-50%,-150%); color:#fff; font-size:12px; font-weight:600;
    white-space:nowrap; text-shadow:0 1px 2px #000, 0 0 5px #000; }
  #legend { position:fixed; bottom:12px; left:12px; z-index:10; background:rgba(16,20,28,.82);
    border:1px solid #2a3340; border-radius:9px; padding:9px 12px; font-size:12px; color:#aab4c2; }
  #legend .bar { height:9px; width:180px; border-radius:5px; margin:5px 0 3px;
    background:linear-gradient(90deg,hsl(205,80%,62%),hsl(285,70%,62%),hsl(20,85%,60%)); }
  #legend .ends { display:flex; justify-content:space-between; }
  #hint { position:fixed; bottom:12px; right:12px; z-index:10; color:#8b97a7; font-size:12px; text-align:right; line-height:1.6; }
  #hint b { color:#c2ccd8; }
  #help { position:fixed; inset:0; z-index:30; display:flex; align-items:center; justify-content:center; background:rgba(5,7,11,.62); touch-action:manipulation; cursor:pointer; }
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
  <div style="display:flex;gap:5px;margin-top:8px">
    <button id="flyBtn" class="ctl">🚀 Fly</button>
    <button id="tourBtn" class="ctl">▶ Tour</button>
    <button id="nameBtn" class="ctl on">🏷 Names</button>
  </div>
  <input id="q" type="search" placeholder="Find a person…" autocomplete="off" style="margin-top:8px">
  <div id="results"></div>
</div>
<div id="legend">Generation
  <div class="bar"></div>
  <div class="ends"><span>0 (you)</span><span>__MAXGEN__</span></div>
</div>
<div id="hint"><b>Drag</b> to rotate · <b>scroll / pinch</b> to zoom · <b>right-drag</b> to slide<br><b>Click a person</b> to fly to them</div>
<div id="flykeys"><b>W A S D</b> to fly · <b>Q / E</b> up &amp; down · <b>Shift</b> = boost · drag to look</div>
<div id="info"></div>
<div id="help" onclick="this.style.display='none'" ontouchend="this.style.display='none'">
  <div class="box">
  <h2>🪐 Flying through the family</h2>
  <ul>
    <li><b>Drag</b> to rotate the whole cloud around</li>
    <li><b>Scroll</b> or pinch to zoom in and out</li>
    <li><b>Right-drag</b> (or two-finger drag) to slide sideways</li>
    <li><b>Click any person</b> to fly the camera to them and light up their connections</li>
    <li><b>Search</b> a name (top-left) to jump straight to anyone</li>
    <li><b>🚀 Fly</b> = steer with <b>W A S D</b> (Q/E up·down, Shift to boost); <b>▶ Tour</b> flies you through the biggest family hubs on its own</li>
    <li><b>🏷 Names</b> shows the nearest people's names automatically — no need to hover</li>
    <li>Click empty space to fly back out</li>
  </ul>
  <button onclick="document.getElementById('help').style.display='none'" ontouchend="document.getElementById('help').style.display='none'">Start exploring →</button>
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

// camera + interaction state
let spin = true;
const ctrl = Graph.controls();
const cam = Graph.camera();
let flyOn = false; const keys = {};
ctrl.addEventListener('start', () => { spin = false; });

// name labels overlay — the names of the nearest people, shown automatically (no hover needed)
const labelsEl = document.createElement('div'); labelsEl.id='labels'; document.body.appendChild(labelsEl);
const labPool = []; const LAB_MAX = 36;
let labelsOn = true;
const tmpV = cam.position.clone();                       // reused Vector3 for projecting nodes onto the screen
function hideLabels(){ for (const el of labPool) el.style.display='none'; }
function updateLabels(){
  if (!labelsOn){ hideLabels(); return; }
  const cp = cam.position;
  const near=[];
  for (const n of CUR.nodes){
    if (n.x==null) continue;
    const vx=n.x-cp.x, vy=n.y-cp.y, vz=n.z-cp.z;
    near.push([vx*vx+vy*vy+vz*vz, n]);                   // rank by distance to the camera
  }
  near.sort((a,b)=>a[0]-b[0]);
  const show = near.slice(0, LAB_MAX);                   // the nearest people always get a name tag
  while (labPool.length<show.length){ const d=document.createElement('div'); d.className='nlab'; labelsEl.appendChild(d); labPool.push(d); }
  for (let i=0;i<labPool.length;i++){
    const el=labPool[i];
    if (i<show.length){
      const n=show[i][1];
      tmpV.set(n.x,n.y,n.z); tmpV.project(cam);           // THREE projection → normalized device coords (no library dependency)
      if (tmpV.z<=1 && tmpV.x>=-1.05 && tmpV.x<=1.05 && tmpV.y>=-1.05 && tmpV.y<=1.05){
        el.textContent=n.name;
        el.style.left=((tmpV.x*0.5+0.5)*innerWidth)+'px';
        el.style.top=((-tmpV.y*0.5+0.5)*innerHeight)+'px';
        el.style.display='block';
      } else el.style.display='none';
    } else el.style.display='none';
  }
}
function flyStep(){                                      // WASD: glide through the cloud (camera + look-target move together)
  if (!flyOn) return;
  const cp=cam.position, tg=ctrl.target;
  let fx=tg.x-cp.x, fy=tg.y-cp.y, fz=tg.z-cp.z; const fl=Math.hypot(fx,fy,fz)||1; fx/=fl; fy/=fl; fz/=fl;
  let rx=-fz, rz=fx; const rl=Math.hypot(rx,rz)||1; rx/=rl; rz/=rl;   // right = forward × up(0,1,0), in the xz-plane
  const s = 24*((keys.ShiftLeft||keys.ShiftRight)?3:1); let dx=0,dy=0,dz=0;
  if (keys.KeyW){ dx+=fx*s; dy+=fy*s; dz+=fz*s; }
  if (keys.KeyS){ dx-=fx*s; dy-=fy*s; dz-=fz*s; }
  if (keys.KeyD){ dx+=rx*s; dz+=rz*s; }
  if (keys.KeyA){ dx-=rx*s; dz-=rz*s; }
  if (keys.KeyE||keys.Space){ dy+=s; }
  if (keys.KeyQ){ dy-=s; }
  if (dx||dy||dz){ cp.x+=dx; cp.y+=dy; cp.z+=dz; tg.x+=dx; tg.y+=dy; tg.z+=dz; if (ctrl.update) ctrl.update(); }
}

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

// one-time "how to navigate" card — tap anywhere on it (button or backdrop) to dismiss; robust on mobile
const helpEl = document.getElementById('help');
function closeHelp(e){ if(e){ e.preventDefault(); e.stopPropagation(); } helpEl.classList.add('hide'); }
helpEl.addEventListener('click', closeHelp);
helpEl.addEventListener('touchend', closeHelp, {passive:false});

// --- controls: fly, tour, names. Wire everything BEFORE starting the render loop. ---
const flyBtn = document.getElementById('flyBtn');
const tourBtn = document.getElementById('tourBtn');
const nameBtn = document.getElementById('nameBtn');

// keyboard fly mode (WASD)
const FLYKEYS = ['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE','Space','ShiftLeft','ShiftRight'];
addEventListener('keydown', e => { if (flyOn && FLYKEYS.includes(e.code)){ keys[e.code]=true; e.preventDefault(); } });
addEventListener('keyup', e => { keys[e.code]=false; });
function setFly(on){ flyOn=on; spin=false; if(on) stopTour();
  flyBtn.classList.toggle('on', on); document.getElementById('flykeys').style.display = on ? 'block' : 'none'; }
flyBtn.addEventListener('click', () => setFly(!flyOn));

// auto-tour: fly from one key ancestor to the next on its own
let tourT=null, tour=[], ti=0;
function stopTour(){ if(tourT){ clearTimeout(tourT); tourT=null; } tourBtn.classList.remove('on'); tourBtn.textContent='▶ Tour'; }
function tourStep(){ if(ti>=tour.length){ stopTour(); return; } focusNode(tour[ti++]); tourT=setTimeout(tourStep, 4800); }
tourBtn.addEventListener('click', () => {
  if (tourT){ stopTour(); return; }
  setFly(false); spin=false;
  tour=[...CUR.nodes].sort((a,b)=>(b.val||0)-(a.val||0)).slice(0,15); ti=0;   // the most-connected family hubs
  tourBtn.classList.add('on'); tourBtn.textContent='⏹ Stop'; tourStep();
});
elem.addEventListener('pointerdown', () => { if(tourT) stopTour(); });   // grabbing the view ends the tour

// names toggle (on by default)
nameBtn.addEventListener('click', () => { labelsOn=!labelsOn; nameBtn.classList.toggle('on', labelsOn); if(!labelsOn) hideLabels(); });

// --- render loop: started last, after every control is wired; one bad frame can't kill it ---
let angle = 0;
(function rotate(){
  try {
    if (spin && !flyOn){ angle += 0.0015; const d = 1400; Graph.cameraPosition({ x: d*Math.sin(angle), z: d*Math.cos(angle) }); }
    flyStep();
    updateLabels();
  } catch (err) { /* never let a single frame stop the loop */ }
  requestAnimationFrame(rotate);
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
