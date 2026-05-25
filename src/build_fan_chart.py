"""Build ``fan.html`` — a 360° ancestor fan chart centered on the root person.

Walks parent links upward from the root and lays every ancestor out as a
proportional (sunburst) wedge: each node's arc is sized to how many ancestors
branch off it, so sparse deep lines spread out instead of crushing together,
while each parent still sits directly outside the child it belongs to.

Rendered on a <canvas> (not thousands of SVG nodes) so pan/zoom stays smooth
even with the full ~2800-person, 19-generation tree; labels are drawn crisply at
the current zoom, and only when they're big enough on screen to read. Click a
wedge to open that person's story; Fernald/Bagley/Both side filter; living
people redacted.

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
        for r in con.execute("SELECT person_id, full_name, birth_date, death_date FROM people")
    }
    parents: dict[str, list[str]] = {}

    def parents_of(pid: str) -> list[str]:
        if pid not in parents:
            rows = con.execute(
                "SELECT person_id FROM family_relationships "
                "WHERE related_person_id = ? AND relationship_type = 'parent' ORDER BY person_id",
                (pid,),
            ).fetchall()
            parents[pid] = [r["person_id"] for r in rows][:2]
        return parents[pid]

    slots: list[dict] = []
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
  #fan { position:fixed; inset:0; display:block; touch-action:none; cursor:grab; }
  #fan:active { cursor:grabbing; }
  #panel { position:fixed; z-index:10; top:10px; left:10px; background:rgba(20,24,32,.82);
    border:1px solid #2a3340; border-radius:9px; padding:10px 13px; backdrop-filter:blur(4px); max-width:62vw; }
  #panel h1 { font-size:15px; margin:0 0 3px; }
  #panel .meta { color:#8b97a7; font-size:11.5px; }
  #panel button { background:#222b38; color:#cdd6e2; border:1px solid #2a3340; border-radius:6px;
    padding:5px 10px; font-size:12px; cursor:pointer; }
  #tip { position:fixed; z-index:20; pointer-events:none; background:rgba(10,12,17,.95);
    border:1px solid #34404f; border-radius:6px; padding:6px 9px; font-size:12.5px; display:none; max-width:240px; }
  #tip b { display:block; }
  #tip span { display:block; color:#9aa6b5; }
  #sides { margin-top:7px; display:flex; gap:5px; }
  #sides button { flex:1; padding:5px 4px; font-size:11.5px; }
  #sides button.on { background:#3a4a5e; color:#fff; border-color:#4a5d75; }
</style>
</head>
<body>
<canvas id="fan"></canvas>
<div id="panel">
  <a href="index.html" style="color:#8b97a7;text-decoration:none;font-size:12px">‹ Home</a>
  <h1>Ancestor fan</h1>
  <div class="meta">__COUNT__ ancestors · __MAXGEN__ generations<br>click a wedge to open that person's story<br>scroll / pinch to zoom · drag to pan</div>
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
<script>
const SLOTS = __DATA__, MAXGEN = Math.max(1, __MAXGEN__), SIDE_LABELS = __SIDELABELS__, SIDE_KEYS = __SIDEKEYS__;
const CR = 76, RW = 86, TAU = Math.PI*2, PAD = 9;
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const firstTwo = s => s.split(' ').slice(0,2).join(' ');
const colorFor = g => `hsl(${210 - (g/MAXGEN)*150}, 52%, ${60 - (g/MAXGEN)*16}%)`;
const sideOf = s => s.gen===0 ? 'root' : ((s.slot >> (s.gen-1))===0 ? 'f' : 'b');

// ---- proportional (sunburst) layout ----
const byKey = new Map(); SLOTS.forEach(s => byKey.set(s.gen+':'+s.slot, s));
function kidsOf(s){ const r=[]; const f=byKey.get((s.gen+1)+':'+(s.slot*2)); const m=byKey.get((s.gen+1)+':'+(s.slot*2+1)); if(f)r.push(f); if(m)r.push(m); return r; }
function weigh(s){ if(s.w!=null) return s.w; const k=kidsOf(s); s.w = k.length ? k.reduce((t,c)=>t+weigh(c),0) : 1; return s.w; }
const ROOT = byKey.get('0:0');
if (ROOT){ weigh(ROOT); ROOT.a0 = -Math.PI/2; ROOT.a1 = -Math.PI/2 + TAU;
  (function assign(s){ let a=s.a0; const span=s.a1-s.a0; for(const c of kidsOf(s)){ c.a0=a; c.a1=a+(c.w/s.w)*span; a=c.a1; assign(c); } })(ROOT);
}
const byGen = {};                                  // for hit-testing
SLOTS.forEach(s => { (byGen[s.gen]=byGen[s.gen]||[]).push(s); });
for (const g in byGen) byGen[g].sort((a,b)=>a.a0-b.a0);

function labelFs(s){
  const span=s.a1-s.a0, midR=CR+(s.gen-0.5)*RW, arc=midR*span, radial=RW-PAD;
  let fs = radial/(Math.max(s.name.length,1)*0.55);
  fs = Math.min(fs, arc*0.82, 15);
  return Math.max(fs, Math.min(3.4, arc*0.82));
}

const cv = document.getElementById('fan'), ctx = cv.getContext('2d');
const dpr = Math.min(window.devicePixelRatio||1, 2);
let view = {k:1, x:0, y:0}, side='', W=0, H=0, _raf=0;

function resize(){ W=innerWidth; H=innerHeight; cv.width=W*dpr; cv.height=H*dpr; cv.style.width=W+'px'; cv.style.height=H+'px'; draw(); }

function draw(){
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,W,H);
  ctx.save();
  ctx.translate(view.x, view.y); ctx.scale(view.k, view.k);
  ctx.lineWidth = Math.max(0.25, 0.6/view.k); ctx.strokeStyle = '#13161d';
  // wedges
  for (const s of SLOTS){
    if (side && s.gen>0 && sideOf(s)!==side) continue;
    const g=s.gen, ri = g===0?0:CR+(g-1)*RW, ro = g===0?CR:CR+g*RW;
    ctx.beginPath();
    if (g===0){ ctx.arc(0,0,CR,0,TAU); }
    else { ctx.arc(0,0,ro,s.a0,s.a1); ctx.arc(0,0,ri,s.a1,s.a0,true); ctx.closePath(); }
    ctx.fillStyle = colorFor(g); ctx.fill();
    if (view.k > 0.18) ctx.stroke();              // skip hairline strokes when zoomed way out
  }
  // labels — only those legible at the current zoom (keeps every frame cheap)
  ctx.textBaseline = 'middle'; ctx.lineJoin = 'round'; ctx.strokeStyle = 'rgba(248,250,252,.7)';
  for (const s of SLOTS){
    if (side && s.gen>0 && sideOf(s)!==side) continue;
    const g=s.gen;
    if (g===0){ ctx.save(); ctx.font='700 14px Segoe UI, sans-serif'; ctx.textAlign='center';
      ctx.fillStyle='#10141b'; ctx.fillText(firstTwo(s.name),0,0); ctx.restore(); continue; }
    const fs = labelFs(s);
    if (fs*view.k < 6) continue;                  // too small on screen to read
    const span=s.a1-s.a0, mid=(s.a0+s.a1)/2, ri=CR+(g-1)*RW, radial=RW-PAD;
    let txt=s.name; const maxChars=Math.floor(radial/(fs*0.55));
    if (txt.length>maxChars) txt=txt.slice(0,Math.max(1,maxChars-1))+'…';
    ctx.save();
    ctx.rotate(mid); ctx.translate(ri+6, 0);
    ctx.font = '600 '+fs.toFixed(1)+'px Segoe UI, sans-serif';
    if (Math.cos(mid) < 0){ ctx.rotate(Math.PI); ctx.textAlign='right'; } else ctx.textAlign='left';
    ctx.lineWidth = Math.max(0.6, fs*0.18);
    ctx.strokeText(txt,0,0); ctx.fillStyle='#10141b'; ctx.fillText(txt,0,0);
    ctx.restore();
  }
  ctx.restore();
}
function schedule(){ if(_raf) return; _raf=requestAnimationFrame(()=>{ _raf=0; draw(); }); }

// ---- view framing ----
function frame(gens){ const R=CR+Math.min(gens,MAXGEN)*RW+20; view.k=Math.min(W,H)/(2*R); view.x=W/2; view.y=H/2; draw(); }
function fit(){ frame(8); }
function fitAll(){ frame(MAXGEN); }
function zoomAround(cx,cy,f){ view.x=cx-(cx-view.x)*f; view.y=cy-(cy-view.y)*f; view.k*=f; schedule(); }

// ---- hit testing (no DOM: from screen point -> wedge) ----
function nodeAt(px,py){
  const wx=(px-view.x)/view.k, wy=(py-view.y)/view.k, r=Math.hypot(wx,wy);
  if (r<=CR) return ROOT;
  const g=Math.floor((r-CR)/RW)+1;
  if (g<1 || g>MAXGEN || !byGen[g]) return null;
  let t=Math.atan2(wy,wx); if (t < -Math.PI/2) t+=TAU;
  for (const s of byGen[g]){ if (t>=s.a0 && t<s.a1) return (side && sideOf(s)!==side) ? null : s; }
  return null;
}

// ---- pan / zoom ----
window.addEventListener('resize', resize);
cv.addEventListener('wheel', e => { e.preventDefault(); zoomAround(e.clientX, e.clientY, e.deltaY<0?1.15:1/1.15); }, {passive:false});
const pts=new Map(); let lastDist=0, lastMid=null, downPt=null, moved=false, lastHover=null;
cv.addEventListener('pointerdown', e => { cv.setPointerCapture(e.pointerId); pts.set(e.pointerId,{x:e.clientX,y:e.clientY}); downPt={x:e.clientX,y:e.clientY}; moved=false; });
cv.addEventListener('pointermove', e => {
  if (pts.has(e.pointerId)){
    const prev=pts.get(e.pointerId); pts.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if (pts.size===1){ view.x+=e.clientX-prev.x; view.y+=e.clientY-prev.y; schedule();
      if (downPt && Math.hypot(e.clientX-downPt.x,e.clientY-downPt.y)>6) moved=true; }
    else if (pts.size===2){ const [a,b]=[...pts.values()]; const d=Math.hypot(a.x-b.x,a.y-b.y); const mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
      if (lastDist){ zoomAround(mid.x,mid.y,d/lastDist); if(lastMid){ view.x+=mid.x-lastMid.x; view.y+=mid.y-lastMid.y; schedule(); } }
      lastDist=d; lastMid=mid; }
    return;
  }
  // hover tooltip (only when not dragging)
  const s=nodeAt(e.clientX,e.clientY);
  if (!s){ tip.style.display='none'; lastHover=null; return; }
  if (s!==lastHover){ lastHover=s;
    tip.innerHTML=`<b>${esc(s.name)}</b><span>${esc([s.born,s.died].filter(Boolean).join(' – ')) || ('generation '+s.gen)}</span>`
      + (s.id?`<span style="color:#8fd3a0">click to open their story →</span>`:''); }
  tip.style.display='block';
  tip.style.left=Math.min(e.clientX+12, innerWidth-tip.offsetWidth-6)+'px';
  tip.style.top=Math.min(e.clientY+12, innerHeight-tip.offsetHeight-6)+'px';
});
function up(e){ pts.delete(e.pointerId); if(pts.size<2){ lastDist=0; lastMid=null; } }
cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
cv.addEventListener('pointerleave', ()=>{ tip.style.display='none'; lastHover=null; });
cv.addEventListener('click', e => {
  if (moved) return;
  const s=nodeAt(e.clientX,e.clientY);
  if (s && s.id) location.href='story.html#'+encodeURIComponent(s.id);
});

// ---- side filter + buttons ----
const sidesEl=document.getElementById('sides');
const opts=[['','Both']].concat(SIDE_KEYS.map(k=>[k==SIDE_KEYS[0]?'f':'b', SIDE_LABELS[k]]));
function paint(){ sidesEl.innerHTML=opts.map(([v,l])=>`<button data-v="${v}" class="${v===side?'on':''}">${esc(l)}</button>`).join(''); }
sidesEl.addEventListener('click', e => { const b=e.target.closest('button'); if(b){ side=b.dataset.v; paint(); draw(); } });
const usp=new URLSearchParams(location.search).get('side');
if (usp===SIDE_KEYS[0]) side='f'; else if (usp===SIDE_KEYS[1]) side='b';
document.getElementById('reset').addEventListener('click', fit);
document.getElementById('all').addEventListener('click', fitAll);
document.getElementById('zin').addEventListener('click', ()=> zoomAround(W/2,H/2,1.5));
document.getElementById('zout').addEventListener('click', ()=> zoomAround(W/2,H/2,1/1.5));

paint(); resize(); fit();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    mg = int(sys.argv[1]) if len(sys.argv) > 1 else MAX_GEN
    print(build(max_gen=mg))
