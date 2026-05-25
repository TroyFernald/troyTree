"""Build ``fan.html`` — a 360° ancestor fan chart centered on the root person.

Walks parent links upward from the root (generation 0) and places each ancestor
in its ahnentafel slot: the person in slot ``s`` of generation ``g`` has parents
in slots ``2s`` and ``2s+1`` of generation ``g+1``. Up to ``MAX_GEN`` rings are
drawn as concentric 360° arcs, colored by generation.

The chart is drawn as SVG in the browser inside a pan/zoom group, with mouse
wheel zoom, drag to pan, and two-finger pinch/pan for touch — so it works on
phones. Tap or hover a wedge for the name and dates.

    python -m src.build_fan_chart [max_gen]
"""

from __future__ import annotations

import json
import sys

from .ancestral_sides import compute_sides
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import LIVING_NAME, is_living

OUT_PATH = EXPORTS_DIR / "fan.html"
MAX_GEN = 25  # effectively "all generations"; the walk stops when parent links run out


def _collect(con, max_gen: int, redact_living: bool = True) -> tuple[list[dict], int]:
    root = con.execute("SELECT person_id FROM people WHERE generation = 0").fetchone()
    if root is None:
        raise SystemExit("No root person (generation 0) found.")
    info = {
        r["person_id"]: r
        for r in con.execute(
            "SELECT person_id, full_name, birth_date, death_date FROM people"
        )
    }
    parents: dict[str, list[str]] = {}

    def parents_of(pid: str) -> list[str]:
        if pid not in parents:
            rows = con.execute(
                "SELECT person_id FROM family_relationships "
                "WHERE related_person_id = ? AND relationship_type = 'parent' "
                "ORDER BY person_id",
                (pid,),
            ).fetchall()
            parents[pid] = [r["person_id"] for r in rows][:2]  # ahnentafel: at most father+mother
        return parents[pid]

    slots: list[dict] = []
    # (person_id, generation, slot index within generation)
    frontier = [(root["person_id"], 0, 0)]
    deepest = 0
    while frontier:
        pid, gen, slot = frontier.pop()
        rec = info.get(pid)
        if rec is None:
            continue
        deepest = max(deepest, gen)
        if redact_living and is_living(rec["birth_date"], rec["death_date"], gen):
            name, born, died = LIVING_NAME, "", ""
        else:
            name = rec["full_name"] or "(unknown)"
            born, died = rec["birth_date"] or "", rec["death_date"] or ""
        slots.append({"id": pid, "gen": gen, "slot": slot, "name": name, "born": born, "died": died})
        if gen < max_gen:
            for i, par in enumerate(parents_of(pid)):
                frontier.append((par, gen + 1, slot * 2 + i))
    return slots, deepest


def build(db_path=WORKING_DB, max_gen: int = MAX_GEN, redact_living: bool = True) -> dict:
    with connect(db_path) as con:
        slots, deepest = _collect(con, max_gen, redact_living)
        _, side_labels, side_keys = compute_sides(con)
    data = json.dumps(slots, ensure_ascii=False).replace("</", "<\\/")
    html_doc = (
        _TEMPLATE.replace("__DATA__", data)
        .replace("__MAXGEN__", str(max(deepest, 1)))
        .replace("__COUNT__", str(len(slots)))
        .replace("__SIDELABELS__", json.dumps(side_labels))
        .replace("__SIDEKEYS__", json.dumps(side_keys))
    )
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"ancestors": len(slots), "generations": deepest, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Troy Family Tree · Fan chart</title>
<style>
  html,body { margin:0; height:100%; background:#13161d; color:#e8e8e8; overflow:hidden;
    font:14px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  #fan { width:100vw; height:100vh; display:block; touch-action:none; cursor:grab; }
  #fan:active { cursor:grabbing; }
  #panel { position:fixed; top:10px; left:10px; z-index:10; background:rgba(20,24,32,.82);
    border:1px solid #2a3340; border-radius:9px; padding:10px 13px; backdrop-filter:blur(4px); max-width:62vw; }
  #panel h1 { font-size:15px; margin:0 0 3px; }
  #panel .meta { color:#8b97a7; font-size:11.5px; }
  #panel button { margin-top:7px; background:#222b38; color:#cdd6e2; border:1px solid #2a3340;
    border-radius:6px; padding:5px 10px; font-size:12px; cursor:pointer; }
  #tip { position:fixed; z-index:20; pointer-events:none; background:rgba(10,12,17,.95);
    border:1px solid #34404f; border-radius:6px; padding:6px 9px; font-size:12.5px; display:none; max-width:240px; }
  #tip b { display:block; }
  #tip span { color:#9aa6b5; }
  #pop { position:fixed; z-index:25; background:rgba(15,18,24,.98); border:1px solid #3a4658;
    border-radius:8px; padding:9px 12px; font-size:13px; display:none; max-width:250px;
    box-shadow:0 6px 24px rgba(0,0,0,.55); }
  #pop.open { display:block; }
  #pop b { display:block; margin-bottom:2px; }
  #pop .d { color:#9aa6b5; font-size:12px; margin-bottom:8px; }
  #pop a { display:inline-block; background:#3a4a5e; color:#fff; text-decoration:none;
    padding:6px 11px; border-radius:6px; font-size:12.5px; }
  #pop a:hover { background:#4a5d75; }
  .wedge { stroke:#13161d; stroke-width:.6; cursor:pointer; }
  .wedge:hover { stroke:#fff; stroke-width:1; }
  text.lbl { fill:#10141b; font-weight:600; pointer-events:none; text-rendering:optimizeSpeed; }
  #vp { will-change:transform; }          /* promote to a GPU layer so pan/zoom is composited, not re-painted */
  #sides { margin-top:7px; display:flex; gap:5px; }
  #sides button { flex:1; background:#222b38; color:#cdd6e2; border:1px solid #2a3340;
    border-radius:6px; padding:5px 4px; font-size:11.5px; cursor:pointer; }
  #sides button.on { background:#3a4a5e; color:#fff; border-color:#4a5d75; }
  svg[data-only="f"] .side-b, svg[data-only="b"] .side-f { display:none; }
</style>
</head>
<body>
<div id="panel">
  <a href="index.html" style="color:#8b97a7;text-decoration:none;font-size:12px">‹ Home</a>
  <h1>Ancestor fan</h1>
  <div class="meta">__COUNT__ ancestors · __MAXGEN__ generations<br>click a wedge for that person (and a link to their story)<br>scroll / pinch to zoom · drag to pan</div>
  <div id="sides"></div>
  <div style="display:flex;gap:5px;margin-top:6px">
    <button id="zout" style="flex:1;font-size:16px">－</button>
    <button id="zin" style="flex:1;font-size:16px">＋</button>
  </div>
  <div style="display:flex;gap:5px;margin-top:5px">
    <button id="reset" style="flex:1">Reset view</button>
    <button id="all" style="flex:1">Whole tree</button>
  </div>
</div>
<div id="tip"></div>
<div id="pop"></div>
<svg id="fan"><g id="vp"></g></svg>
<script>
const SLOTS = __DATA__;
const MAXGEN = Math.max(1, __MAXGEN__);
const SIDE_LABELS = __SIDELABELS__;
const SIDE_KEYS = __SIDEKEYS__;
const sideClass = s => s.gen===0 ? 'side-root' : ((s.slot >> (s.gen-1))===0 ? 'side-f' : 'side-b');
const CR = 76, RW = 86;                  // center radius, ring width
const TAU = Math.PI*2;
const LABEL_MAX = 99;                     // label every generation (tiny far out; zoom in to read)
// Cool blue → teal → green → soft gold sweep (no red), darkening gently outward
const colorFor = g => `hsl(${210 - (g/MAXGEN)*150}, 52%, ${60 - (g/MAXGEN)*16}%)`;
const polar = (r,a) => [r*Math.cos(a), r*Math.sin(a)];

// ---- proportional (sunburst) layout ----------------------------------------
// Each node claims an arc sized to how many ancestors branch off it, so sparse
// deep lines spread into the empty space instead of piling onto adjacent slots,
// while every parent still sits directly outside the child it belongs to.
const PAD = 9;
const firstTwo = s => s.split(' ').slice(0,2).join(' ');
const byKey = new Map();
for (const s of SLOTS) byKey.set(s.gen+':'+s.slot, s);
function kidsOf(s){ const r=[]; const f=byKey.get((s.gen+1)+':'+(s.slot*2)); const m=byKey.get((s.gen+1)+':'+(s.slot*2+1)); if(f)r.push(f); if(m)r.push(m); return r; }
function weigh(s){ if(s.w!=null) return s.w; const k=kidsOf(s); s.w = k.length ? k.reduce((t,c)=>t+weigh(c),0) : 1; return s.w; }
const ROOT = byKey.get('0:0');
if (ROOT){ weigh(ROOT); ROOT.a0 = -Math.PI/2; ROOT.a1 = -Math.PI/2 + TAU;
  (function assign(s){ let a=s.a0; const span=s.a1-s.a0; for(const c of kidsOf(s)){ c.a0=a; c.a1=a+(c.w/s.w)*span; a=c.a1; assign(c); } })(ROOT);
}

function sector(s) {
  const g=s.gen, ri = g===0 ? 0 : CR + (g-1)*RW, ro = g===0 ? CR : CR + g*RW;
  if (g===0) return `M ${-ri} 0 A ${ri} ${ri} 0 1 1 ${ri} 0 A ${ri} ${ri} 0 1 1 ${-ri} 0 Z`;
  const a0=s.a0, a1=s.a1;
  const [x0,y0]=polar(ri,a0),[x1,y1]=polar(ro,a0),[x2,y2]=polar(ro,a1),[x3,y3]=polar(ri,a1);
  const large = (a1-a0)>Math.PI ? 1 : 0;
  return `M ${x0} ${y0} L ${x1} ${y1} A ${ro} ${ro} 0 ${large} 1 ${x2} ${y2} `
       + `L ${x3} ${y3} A ${ri} ${ri} 0 ${large} 0 ${x0} ${y0} Z`;
}

function label(s) {
  const g=s.gen, name=s.name;
  if (g===0) return {radial:false, fs:14, txt:firstTwo(name)};
  // Auto-fit: shrink the font so the WHOLE name fits along the ring width, and
  // never let it grow taller than the wedge is thick (so it stays inside the box).
  const span = s.a1 - s.a0, mid = (s.a0 + s.a1)/2;
  const midR = CR + (g-0.5)*RW;
  const arcThick = midR * span;                 // room across the wedge (perpendicular)
  const radialRoom = RW - PAD;                  // room along the radius (text length)
  const cap = arcThick * 0.82;                  // hard cap: never taller than the wedge (prevents overlap)
  let fs = radialRoom / (Math.max(name.length,1) * 0.55);
  fs = Math.min(fs, cap, 15);
  fs = Math.max(fs, Math.min(3.4, cap));        // floor, but never above the cap
  let txt = name;
  const maxChars = Math.floor(radialRoom / (fs*0.55));   // truncate only if even the floor won't fit
  if (txt.length > maxChars) txt = txt.slice(0, Math.max(1, maxChars-1)) + '…';
  let deg = mid*180/Math.PI, anchor='start', flip=0;
  if (deg>90 || deg<-90) { flip=180; anchor='end'; }
  return {radial:true, deg, anchor, flip, fs, txt};
}

const vp = document.getElementById('vp');
let frag = '';
SLOTS.forEach((s, i) => {                        // index instead of O(n^2) indexOf
  frag += `<path class="wedge ${sideClass(s)}" d="${sector(s)}" fill="${colorFor(s.gen)}" data-i="${i}"></path>`;
});
for (const s of SLOTS) {
  if (s.gen > LABEL_MAX) continue;
  const L = label(s);
  if (L.radial) {
    frag += `<g class="${sideClass(s)}" transform="rotate(${L.deg}) translate(${CR + (s.gen-1)*RW + 6} 0) rotate(${L.flip})">`
          + `<text class="lbl" x="0" y="0" font-size="${L.fs.toFixed(1)}" dominant-baseline="middle" text-anchor="${L.anchor}">${esc(L.txt)}</text></g>`;
  } else {
    frag += `<text class="lbl side-root" x="0" y="0" font-size="${L.fs}" text-anchor="middle" dominant-baseline="middle">${esc(L.txt)}</text>`;
  }
}
vp.innerHTML = frag;
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

// ---- pan / zoom (mouse wheel, drag, two-finger pinch) ----
const svg = document.getElementById('fan');
let view = {k:1, x:0, y:0}, _raf=0;
function apply(){ if(_raf) return;               // coalesce many pointer/wheel events into one paint per frame
  _raf = requestAnimationFrame(()=>{ _raf=0; vp.setAttribute('transform', `translate(${view.x} ${view.y}) scale(${view.k})`); }); }
function frame(gens){
  // Zoom so `gens` rings fill the viewport (names stay readable); deeper rings sit
  // beyond the edges and can be reached by zooming out or panning.
  const R = CR + Math.min(gens, MAXGEN)*RW + 20, w = svg.clientWidth, h = svg.clientHeight;
  view.k = Math.min(w, h) / (2*R); view.x = w/2; view.y = h/2; apply();
}
function fit(){ frame(8); }          // default: the readable inner generations
function fitAll(){ frame(MAXGEN); }  // the whole tree at once
addEventListener('resize', fit);

svg.addEventListener('wheel', e => {
  e.preventDefault();
  const f = e.deltaY<0 ? 1.12 : 1/1.12;
  zoomAround(e.clientX, e.clientY, f);
}, {passive:false});
function zoomAround(cx, cy, f){
  view.x = cx - (cx-view.x)*f; view.y = cy - (cy-view.y)*f; view.k *= f; apply();
}

const pts = new Map(); let lastDist=0, lastMid=null, downPt=null, moved=false;
svg.addEventListener('pointerdown', e => { svg.setPointerCapture(e.pointerId); pts.set(e.pointerId,{x:e.clientX,y:e.clientY}); downPt={x:e.clientX,y:e.clientY}; moved=false; pop.classList.remove('open'); });
svg.addEventListener('pointermove', e => {
  if (!pts.has(e.pointerId)) return;
  const prev = pts.get(e.pointerId); pts.set(e.pointerId,{x:e.clientX,y:e.clientY});
  if (pts.size===1){ view.x += e.clientX-prev.x; view.y += e.clientY-prev.y; apply();
    if (downPt && Math.hypot(e.clientX-downPt.x, e.clientY-downPt.y)>6) moved=true; }
  else if (pts.size===2){
    const [a,b]=[...pts.values()]; const dist=Math.hypot(a.x-b.x,a.y-b.y);
    const mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
    if (lastDist){ zoomAround(mid.x,mid.y,dist/lastDist);
      if(lastMid){ view.x += mid.x-lastMid.x; view.y += mid.y-lastMid.y; apply(); } }
    lastDist=dist; lastMid=mid;
  }
});
function up(e){ pts.delete(e.pointerId); if(pts.size<2){lastDist=0;lastMid=null;} }
svg.addEventListener('pointerup', up); svg.addEventListener('pointercancel', up);

// ---- tooltip ----
const tip = document.getElementById('tip');
function show(i, x, y){
  const s = SLOTS[i]; if(!s) return;
  tip.innerHTML = `<b>${esc(s.name)}</b><span>${esc([s.born,s.died].filter(Boolean).join(' – ')) || 'gen '+s.gen}</span>`
    + (s.id ? `<span style="color:#8fd3a0">click for their story →</span>` : '');
  tip.style.display='block';
  tip.style.left = Math.min(x+12, innerWidth-tip.offsetWidth-6)+'px';
  tip.style.top = Math.min(y+12, innerHeight-tip.offsetHeight-6)+'px';
}
let lastHover=-1;
svg.addEventListener('pointermove', e => {
  if (pts.size){ tip.style.display='none'; lastHover=-1; return; }   // panning/pinching: no tooltip
  const t = e.target.closest('.wedge');
  if (!t){ if(lastHover!==-1){ tip.style.display='none'; lastHover=-1; } return; }
  const i = +t.dataset.i;
  if (i!==lastHover){ lastHover=i; show(i, e.clientX, e.clientY); }   // rebuild only when wedge changes
  else { tip.style.left=Math.min(e.clientX+12, innerWidth-tip.offsetWidth-6)+'px';
         tip.style.top=Math.min(e.clientY+12, innerHeight-tip.offsetHeight-6)+'px'; }
});
svg.addEventListener('pointerleave', ()=> tip.style.display='none');
const pop=document.getElementById('pop');
function showPop(i, x, y){
  const s=SLOTS[i]; if(!s) return;
  pop.innerHTML=`<b>${esc(s.name)}</b><div class="d">${esc([s.born,s.died].filter(Boolean).join(' – ')) || ('Generation '+s.gen)}</div>`
    + (s.id ? `<a href="story.html#${encodeURIComponent(s.id)}">📖 Open their story →</a>` : '');
  pop.classList.add('open');
  pop.style.left=Math.min(x+10, innerWidth-pop.offsetWidth-8)+'px';
  pop.style.top=Math.min(y+10, innerHeight-pop.offsetHeight-8)+'px';
}
svg.addEventListener('click', e => {
  const t=e.target.closest('.wedge');
  if(!t || moved){ if(!t) pop.classList.remove('open'); return; }   // pan, or click on empty space
  tip.style.display='none';
  showPop(+t.dataset.i, e.clientX, e.clientY);
});
addEventListener('keydown', e => { if(e.key==='Escape') pop.classList.remove('open'); });
document.getElementById('reset').addEventListener('click', fit);
document.getElementById('all').addEventListener('click', fitAll);
document.getElementById('zin').addEventListener('click', ()=> zoomAround(innerWidth/2, innerHeight/2, 1.5));
document.getElementById('zout').addEventListener('click', ()=> zoomAround(innerWidth/2, innerHeight/2, 1/1.5));

// ---- Fernald / Bagley side toggle ----
const sidesEl = document.getElementById('sides');
const sideBtns = [['','Both'], ['f', SIDE_LABELS[SIDE_KEYS[0]]||'Paternal'], ['b', SIDE_LABELS[SIDE_KEYS[1]]||'Maternal']];
sidesEl.innerHTML = sideBtns.map(([v,l]) => `<button data-only="${v}">${esc(l)}</button>`).join('');
function setOnly(v){ if(v) svg.dataset.only=v; else svg.removeAttribute('data-only');
  [...sidesEl.children].forEach(b => b.classList.toggle('on', b.dataset.only===v)); }
sidesEl.addEventListener('click', e => { const b=e.target.closest('button'); if(b) setOnly(b.dataset.only); });
const usp = new URLSearchParams(location.search).get('side');
setOnly(usp===SIDE_KEYS[0] ? 'f' : usp===SIDE_KEYS[1] ? 'b' : '');

fit();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    mg = int(sys.argv[1]) if len(sys.argv) > 1 else MAX_GEN
    print(build(max_gen=mg))
