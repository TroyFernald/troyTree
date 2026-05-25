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
  .wedge { stroke:#13161d; stroke-width:.6; cursor:pointer; }
  .wedge:hover { stroke:#fff; stroke-width:1; }
  text.lbl { fill:#10141b; font-weight:600; pointer-events:none;
    paint-order:stroke; stroke:rgba(248,250,252,.62); stroke-width:1.5px; stroke-linejoin:round; }
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
  <div class="meta">__COUNT__ ancestors · __MAXGEN__ generations<br>click a wedge to open that person's story · zoom in to read the outer rings<br>scroll / pinch to zoom · drag to pan</div>
  <div id="sides"></div>
  <button id="reset" style="margin-top:6px">Reset view</button>
</div>
<div id="tip"></div>
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
const MINSPAN = 0.012;                    // min wedge angle (~0.7°) so sparse deep ancestors stay visible
// Cool blue → teal → green → soft gold sweep (no red), darkening gently outward
const colorFor = g => `hsl(${210 - (g/MAXGEN)*150}, 52%, ${60 - (g/MAXGEN)*16}%)`;
const polar = (r,a) => [r*Math.cos(a), r*Math.sin(a)];

function sector(g, slot) {
  const n = Math.pow(2, g), nat = TAU/n;
  const mid = -Math.PI/2 + (slot+0.5)*nat;               // wedge centre, starting at top, clockwise
  const span = Math.max(nat, MINSPAN);                   // clamp so deep, sparse wedges remain visible
  const a0 = mid - span/2, a1 = mid + span/2;
  const ri = g===0 ? 0 : CR + (g-1)*RW, ro = g===0 ? CR : CR + g*RW;
  if (g===0) return `M ${-ri} 0 A ${ri} ${ri} 0 1 1 ${ri} 0 A ${ri} ${ri} 0 1 1 ${-ri} 0 Z`;
  const [x0,y0]=polar(ri,a0),[x1,y1]=polar(ro,a0),[x2,y2]=polar(ro,a1),[x3,y3]=polar(ri,a1);
  const large = span>Math.PI ? 1 : 0;
  return `M ${x0} ${y0} L ${x1} ${y1} A ${ro} ${ro} 0 ${large} 1 ${x2} ${y2} `
       + `L ${x3} ${y3} A ${ri} ${ri} 0 ${large} 0 ${x0} ${y0} Z`;
}

const PAD = 9;                                  // radial padding inside a ring
function label(g, slot, name) {
  const n = Math.pow(2, g), span = TAU/n, mid = -Math.PI/2 + (slot+0.5)*span;
  if (g===0) return {radial:false, fs:14, txt:firstTwo(name)};
  // Auto-fit: shrink the font so the WHOLE name fits along the ring width, and
  // never let it grow taller than the wedge is thick (so it stays inside the box).
  const drawnSpan = Math.max(span, MINSPAN);
  const midR = CR + (g-0.5)*RW;
  const arcThick = midR * drawnSpan;            // room across the wedge (perpendicular)
  const radialRoom = RW - PAD;                  // room along the radius (text length)
  let fs = radialRoom / (Math.max(name.length,1) * 0.55);
  fs = Math.min(fs, arcThick * 0.80, 15);       // cap by wedge thickness and a sensible max
  fs = Math.max(fs, 3.4);                        // floor
  let txt = name;
  const maxChars = Math.floor(radialRoom / (fs*0.55));   // truncate only if even the floor won't fit
  if (txt.length > maxChars) txt = txt.slice(0, Math.max(1, maxChars-1)) + '…';
  let deg = mid*180/Math.PI, anchor='start', flip=0;
  if (deg>90 || deg<-90) { flip=180; anchor='end'; }
  return {radial:true, deg, anchor, flip, fs, txt};
}
const firstTwo = s => s.split(' ').slice(0,2).join(' ');

const vp = document.getElementById('vp');
let frag = '';
for (const s of SLOTS) {
  frag += `<path class="wedge ${sideClass(s)}" d="${sector(s.gen,s.slot)}" fill="${colorFor(s.gen)}"`
        + ` data-i="${SLOTS.indexOf(s)}"></path>`;
}
for (const s of SLOTS) {
  if (s.gen > LABEL_MAX) continue;             // (labels on every generation; zoom in to read the outer rim)
  const L = label(s.gen, s.slot, s.name);
  const sw = Math.max(0.4, L.fs*0.16).toFixed(2);
  if (L.radial) {
    frag += `<g class="${sideClass(s)}" transform="rotate(${L.deg}) translate(${CR + (s.gen-1)*RW + 6} 0) rotate(${L.flip})">`
          + `<text class="lbl" x="0" y="0" font-size="${L.fs.toFixed(1)}" style="stroke-width:${sw}px" dominant-baseline="middle" text-anchor="${L.anchor}">${esc(L.txt)}</text></g>`;
  } else {
    frag += `<text class="lbl side-root" x="0" y="0" font-size="${L.fs}" style="stroke-width:${sw}px" text-anchor="middle" dominant-baseline="middle">${esc(L.txt)}</text>`;
  }
}
vp.innerHTML = frag;
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

// ---- pan / zoom (mouse wheel, drag, two-finger pinch) ----
const svg = document.getElementById('fan');
let view = {k:1, x:0, y:0};
function apply(){ vp.setAttribute('transform', `translate(${view.x} ${view.y}) scale(${view.k})`); }
function fit(){
  const R = CR + MAXGEN*RW + 30, w = svg.clientWidth, h = svg.clientHeight;
  view.k = Math.min(w, h) / (2*R); view.x = w/2; view.y = h/2; apply();
}
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
svg.addEventListener('pointerdown', e => { svg.setPointerCapture(e.pointerId); pts.set(e.pointerId,{x:e.clientX,y:e.clientY}); downPt={x:e.clientX,y:e.clientY}; moved=false; });
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
svg.addEventListener('pointermove', e => {
  const t = e.target.closest('.wedge');
  if (t && pts.size===0) show(+t.dataset.i, e.clientX, e.clientY); else if(pts.size) tip.style.display='none';
});
svg.addEventListener('pointerleave', ()=> tip.style.display='none');
svg.addEventListener('click', e => {
  const t=e.target.closest('.wedge'); if(!t || moved) return;     // ignore clicks that were pans
  const s=SLOTS[+t.dataset.i];
  if(s && s.id) location.href='story.html#'+encodeURIComponent(s.id);
});
document.getElementById('reset').addEventListener('click', fit);

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
