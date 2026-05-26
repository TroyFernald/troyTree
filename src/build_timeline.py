"""Build ``timeline.html`` — the whole family laid out in time.

Every relative with a known year becomes a lifespan bar (birth → death), packed
into lanes so thousands fit without overlap. Rendered on a <canvas> (not
thousands of DOM nodes) so horizontal zoom across five centuries and pan stay
smooth. Bars are colored by family side; click any bar to open that person's
story. Living people are redacted.

    python -m src.build_timeline
"""

from __future__ import annotations

import json
import re

from .ancestral_sides import compute_sides
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import is_living

OUT_PATH = EXPORTS_DIR / "timeline.html"
_YEAR = re.compile(r"\b(1[0-9]\d\d|20\d\d)\b")


def _year(s: str | None):
    m = _YEAR.search(s or "")
    return int(m.group(1)) if m else None


def _collect(con, redact_living: bool) -> list[dict]:
    sides, _, _ = compute_sides(con)
    story_ids = set()
    sp = EXPORTS_DIR / "story_ids.json"
    if sp.exists():
        try:
            story_ids = set(json.loads(sp.read_text(encoding="utf-8")))
        except Exception:
            story_ids = set()
    people = []
    for p in con.execute(
        "SELECT person_id, full_name, birth_date, death_date, generation FROM people"
    ):
        if redact_living and is_living(p["birth_date"], p["death_date"], p["generation"]):
            continue
        b, d = _year(p["birth_date"]), _year(p["death_date"])
        if b is None and d is None:
            continue
        people.append({
            "id": p["person_id"],
            "n": p["full_name"] or "(unknown)",
            "b": b, "d": d,
            "g": p["generation"],
            "s": sides.get(p["person_id"], []),
            "st": 1 if p["person_id"] in story_ids else 0,
        })
    # earliest first — nicer initial lane packing
    people.sort(key=lambda x: (x["b"] if x["b"] is not None else x["d"], x["d"] or 9999))
    return people


def build(db_path=WORKING_DB, redact_living: bool = True) -> dict:
    with connect(db_path) as con:
        people = _collect(con, redact_living)
        _, side_labels, side_keys = compute_sides(con)
    yrs = [y for p in people for y in (p["b"], p["d"]) if y]
    span = [min(yrs), max(yrs)] if yrs else [1600, 2025]
    data = json.dumps(people, ensure_ascii=False).replace("</", "<\\/")
    html_doc = (
        _TEMPLATE.replace("__DATA__", data)
        .replace("__COUNT__", str(len(people)))
        .replace("__MINY__", str(span[0]))
        .replace("__MAXY__", str(span[1]))
        .replace("__SIDELABELS__", json.dumps(side_labels))
        .replace("__SIDEKEYS__", json.dumps(side_keys))
    )
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"people": len(people), "span": span, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Troy Family Tree · Timeline</title>
<style>
  html,body { margin:0; height:100%; background:#13161d; color:#e8e8e8; overflow:hidden;
    font:14px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  #tl { position:fixed; inset:0; display:block; touch-action:none; cursor:grab; }
  #tl:active { cursor:grabbing; }
  #panel { position:fixed; z-index:10; top:10px; left:10px; background:rgba(20,24,32,.82);
    border:1px solid #2a3340; border-radius:9px; padding:10px 13px; backdrop-filter:blur(4px); max-width:64vw; }
  #panel h1 { font-size:15px; margin:0 0 3px; }
  #panel .meta { color:#8b97a7; font-size:11.5px; line-height:1.5; }
  #panel a.home { color:#8b97a7; text-decoration:none; font-size:12px; }
  #panel button { background:#222b38; color:#cdd6e2; border:1px solid #2a3340; border-radius:6px;
    padding:5px 10px; font-size:12px; cursor:pointer; }
  #sides { margin-top:7px; display:flex; gap:5px; }
  #sides button { flex:1; padding:5px 4px; font-size:11.5px; }
  #sides button.on { background:#3a4a5e; color:#fff; border-color:#4a5d75; }
  #q { width:100%; margin-top:7px; padding:6px 8px; border:1px solid #2a3340; border-radius:6px;
    background:#0d1119; color:#e8e8e8; font-size:12.5px; }
  #tip { position:fixed; z-index:20; pointer-events:none; background:rgba(10,12,17,.96);
    border:1px solid #34404f; border-radius:6px; padding:6px 9px; font-size:12.5px; display:none; max-width:250px; }
  #tip b { display:block; } #tip span { display:block; color:#9aa6b5; }
  #legend { position:fixed; z-index:10; right:10px; bottom:10px; background:rgba(20,24,32,.82);
    border:1px solid #2a3340; border-radius:8px; padding:7px 11px; font-size:11.5px; color:#aab4c2; }
  #legend i { display:inline-block; width:11px; height:11px; border-radius:2px; margin-right:5px; vertical-align:-1px; }
</style>
</head>
<body>
<canvas id="tl"></canvas>
<div id="panel">
  <a class="home" href="index.html">‹ Home</a>
  <h1>Family Timeline</h1>
  <div class="meta">__COUNT__ relatives · __MINY__–__MAXY__<br><b>each band = a generation</b> (you at top, ancestors below)<br>each bar = one life (birth → death)<br>scroll / pinch to zoom time · drag to pan · click a life for their story</div>
  <div id="sides"></div>
  <input id="q" type="search" placeholder="Find &amp; jump to a person…" autocomplete="off">
  <div style="display:flex;gap:5px;margin-top:6px">
    <button id="zout" style="flex:1;font-size:16px">－</button>
    <button id="zin" style="flex:1;font-size:16px">＋</button>
    <button id="reset" style="flex:2">Fit all</button>
  </div>
</div>
<div id="tip"></div>
<div id="legend"></div>
<script>
const PEOPLE = __DATA__, SIDE_LABELS = __SIDELABELS__, SIDE_KEYS = __SIDEKEYS__;
const MINY = __MINY__, MAXY = __MAXY__;
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const FK = SIDE_KEYS[0], BK = SIDE_KEYS[1];
const colFor = p => p.s && p.s.includes(FK) ? '#5b9bd5' : (p.s && p.s.includes(BK) ? '#d59a4e' : '#6bbf86');

const cv = document.getElementById('tl'), ctx = cv.getContext('2d');
const dpr = Math.min(window.devicePixelRatio||1, 2);
const LH = 12, BAR = 8, AXIS_H = 30, LEFTW = 108, BANDGAP = 1;   // compact lanes; left label gutter; blank row between generations
let W=0, H=0, scaleX=1, panX=0, panY=AXIS_H+8, side='', totalRows=0, _raf=0, _q='';
const tip = document.getElementById('tip');
function genLabel(g){
  if (g>=900) return ['Other','relatives'];
  if (g===0) return ['Gen 0','You'];
  if (g===1) return ['Gen 1','Parents'];
  if (g===2) return ['Gen 2','Grandparents'];
  if (g===3) return ['Gen 3','Gt-grandparents'];
  return ['Gen '+g, (g-2)+'×-gt grandparents'];
}

// ---- layout: one band per generation (You at top, ancestors below); pack lives into lanes WITHIN each band ----
let LANES = [], BANDS = [];
function repack(){
  LANES = PEOPLE.filter(p => !side || (p.s && p.s.includes(side)))
                .filter(p => !_q || p.n.toLowerCase().includes(_q));
  for (const p of LANES){
    const st = (p.b!=null?p.b:p.d), en = (p.d!=null?p.d:p.b);
    p._s = st; p._e = Math.max(en, st+1); p._pt = (p.b==null||p.d==null);   // _pt = single-date point
  }
  const groups = new Map();                       // generation -> people (no generation -> 999)
  for (const p of LANES){ const g = (p.g==null?999:p.g); (groups.get(g)||groups.set(g,[]).get(g)).push(p); }
  const gens = [...groups.keys()].sort((a,b)=>a-b);
  BANDS = []; let row = 0;
  for (const g of gens){
    const arr = groups.get(g); arr.sort((a,b)=> a._s-b._s || a._e-b._e);
    const ends = [];                              // greedy lane packing within this generation
    for (const p of arr){
      let placed=false;
      for (let i=0;i<ends.length;i++){ if (ends[i] < p._s){ p._row=row+i; ends[i]=p._e; placed=true; break; } }
      if (!placed){ p._row=row+ends.length; ends.push(p._e); }
    }
    BANDS.push({ g, label: genLabel(g), rowStart: row, rows: Math.max(1, ends.length) });
    row += Math.max(1, ends.length) + BANDGAP;
  }
  totalRows = row;
}

// ---- coordinate transforms ----
const yearToX = y => panX + y*scaleX;
const xToYear = x => (x - panX)/scaleX;
const laneToY = l => panY + l*LH;

function clampPan(){
  const totalH = totalRows*LH + 20;
  const minPanY = Math.min(AXIS_H+8, H - totalH - 8);
  if (panY > AXIS_H+8) panY = AXIS_H+8;
  if (panY < minPanY) panY = minPanY;
}

// ---- nice gridline step so labels are ~110px apart ----
const STEPS = [1,2,5,10,25,50,100,200,500,1000];
function niceStep(minYears){ for (const s of STEPS) if (s>=minYears) return s; return 1000; }

function draw(){
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,W,H);
  clampPan();
  const y0=xToYear(0), y1=xToYear(W);

  // generation band stripes + separator lines
  for (let i=0;i<BANDS.length;i++){
    const bd=BANDS[i], top=laneToY(bd.rowStart), h=bd.rows*LH;
    if (top+h < AXIS_H || top > H) continue;
    ctx.fillStyle = (bd.g>=900) ? 'rgba(90,100,120,.10)' : (i%2 ? 'rgba(120,140,170,.05)' : 'rgba(120,140,170,.11)');
    const ytop=Math.max(top,AXIS_H); ctx.fillRect(0, ytop, W, top+h-ytop);
    ctx.strokeStyle='rgba(120,140,170,.20)'; ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(0,top); ctx.lineTo(W,top); ctx.stroke();
  }

  // year gridlines
  const step = niceStep(110/scaleX);
  const start = Math.floor(y0/step)*step;
  for (let y=start; y<=y1; y+=step){
    const x=yearToX(y);
    ctx.strokeStyle = (y%(step*5)===0)?'rgba(120,140,170,.22)':'rgba(120,140,170,.09)';
    ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(x,AXIS_H); ctx.lineTo(x,H); ctx.stroke();
  }

  // lifespan bars (cull to what's on screen)
  const lo=Math.floor((-LH-panY)/LH), hi=Math.ceil((H-panY)/LH);
  ctx.textBaseline='middle';
  for (const p of LANES){
    if (p._row<lo || p._row>hi) continue;
    if (p._e < y0 || p._s > y1) continue;
    const x0=yearToX(p._s), x1=yearToX(p._e), yy=laneToY(p._row)+(LH-BAR)/2, w=Math.max(2, x1-x0);
    ctx.globalAlpha = p.st ? 1 : 0.7;
    ctx.fillStyle = colFor(p);
    if (p._pt){ const cx=x0+1.5, cy=yy+BAR/2, r=BAR/1.7;       // single-date life = diamond marker
      ctx.beginPath(); ctx.moveTo(cx,cy-r); ctx.lineTo(cx+r,cy); ctx.lineTo(cx,cy+r); ctx.lineTo(cx-r,cy); ctx.closePath(); ctx.fill(); }
    else ctx.fillRect(x0, yy, w, BAR);
    if (w>34 || (p._pt && scaleX>3)){                          // name printed on the bar when it's wide enough
      ctx.globalAlpha=1; ctx.fillStyle='#0c0f15'; ctx.font='600 9px Segoe UI, sans-serif';
      let t=p.n; const room=Math.max(w-6, p._pt?90:0), maxc=Math.floor(room/5.2);
      if (t.length>maxc) t=t.slice(0,Math.max(1,maxc-1))+'…';
      if (maxc>=2) ctx.fillText(t, (p._pt?x0+8:x0+4), yy+BAR/2+0.5);
    }
    ctx.globalAlpha=1;
  }
  ctx.textBaseline='alphabetic';

  // top axis band with year labels
  ctx.fillStyle='rgba(14,17,23,.93)'; ctx.fillRect(0,0,W,AXIS_H);
  ctx.strokeStyle='rgba(120,140,170,.25)'; ctx.beginPath(); ctx.moveTo(0,AXIS_H); ctx.lineTo(W,AXIS_H); ctx.stroke();
  ctx.fillStyle='#cdd6e2'; ctx.font='600 12px Segoe UI, sans-serif'; ctx.textBaseline='middle'; ctx.textAlign='center';
  for (let y=start; y<=y1; y+=step){ if (step>=100 || y%(step*5)===0){ const x=yearToX(y); if(x>LEFTW+18 && x<W-6) ctx.fillText(y, x, AXIS_H/2); } }
  ctx.textAlign='left';

  // left sticky generation-label gutter (drawn last so it stays on top)
  ctx.fillStyle='rgba(14,17,23,.9)'; ctx.fillRect(0,AXIS_H,LEFTW,H-AXIS_H);
  ctx.strokeStyle='rgba(120,140,170,.25)'; ctx.beginPath(); ctx.moveTo(LEFTW,AXIS_H); ctx.lineTo(LEFTW,H); ctx.stroke();
  ctx.textBaseline='middle';
  for (const bd of BANDS){
    const top=laneToY(bd.rowStart), h=bd.rows*LH; if (top+h<AXIS_H+4 || top>H) continue;
    let cy=Math.max(AXIS_H+14, Math.min(top+h/2, H-10)); cy=Math.max(cy, top+13); cy=Math.min(cy, top+h-4);
    ctx.fillStyle='#dbe3ee'; ctx.font='700 11px Segoe UI, sans-serif'; ctx.fillText(bd.label[0], 9, cy-6);
    ctx.fillStyle='#8b97a7'; ctx.font='10px Segoe UI, sans-serif'; ctx.fillText(bd.label[1], 9, cy+6);
  }
  ctx.textBaseline='alphabetic';
}
function schedule(){ if(_raf) return; _raf=requestAnimationFrame(()=>{ _raf=0; draw(); }); }

// ---- view framing ----
function resize(){ W=innerWidth; H=innerHeight; cv.width=W*dpr; cv.height=H*dpr; cv.style.width=W+'px'; cv.style.height=H+'px'; draw(); }
function fitAll(){ const pad=8, left=LEFTW+16; scaleX=(W-left-24)/Math.max(1,(MAXY-MINY+pad)); panX=left - MINY*scaleX; panY=AXIS_H+8; draw(); }
function zoomAround(cx, f){ const yr=xToYear(cx); scaleX=Math.min(60, Math.max( (W)/(MAXY-MINY+400), scaleX*f)); panX=cx - yr*scaleX; schedule(); }

// ---- hit testing: screen point -> life bar ----
function hit(px,py){
  if (py<AXIS_H) return null;
  const row=Math.floor((py-panY)/LH);
  let best=null, bestd=1e9;
  for (const p of LANES){
    if (p._row!==row) continue;
    const x0=yearToX(p._s), x1=Math.max(yearToX(p._e), x0+ (p._pt?12:2));
    if (px>=x0-6 && px<=x1+2){ const d=Math.abs(px-(x0+x1)/2); if(d<bestd){bestd=d; best=p;} }
  }
  return best;
}

// ---- pan / zoom / interaction ----
addEventListener('resize', resize);
cv.addEventListener('wheel', e => { e.preventDefault();
  if (e.shiftKey){ panY -= e.deltaY; schedule(); }                 // shift+wheel = scroll lanes
  else zoomAround(e.clientX, e.deltaY<0?1.15:1/1.15); }, {passive:false});
const pts=new Map(); let lastDist=0, lastMid=null, downPt=null, moved=false, lastHover=null;
cv.addEventListener('pointerdown', e => { cv.setPointerCapture(e.pointerId); pts.set(e.pointerId,{x:e.clientX,y:e.clientY}); downPt={x:e.clientX,y:e.clientY}; moved=false; });
cv.addEventListener('pointermove', e => {
  if (pts.has(e.pointerId)){
    const prev=pts.get(e.pointerId); pts.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if (pts.size===1){ panX+=e.clientX-prev.x; panY+=e.clientY-prev.y; schedule();
      if (downPt && Math.hypot(e.clientX-downPt.x,e.clientY-downPt.y)>6) moved=true; }
    else if (pts.size===2){ const [a,b]=[...pts.values()]; const d=Math.hypot(a.x-b.x,a.y-b.y); const mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
      if (lastDist){ zoomAround(mid.x, d/lastDist); if(lastMid){ panX+=mid.x-lastMid.x; panY+=mid.y-lastMid.y; schedule(); } }
      lastDist=d; lastMid=mid; }
    return;
  }
  const p=hit(e.clientX,e.clientY);
  if (!p){ tip.style.display='none'; lastHover=null; return; }
  if (p!==lastHover){ lastHover=p;
    const yrs=[p.b,p.d].filter(v=>v!=null).join(' – ');
    tip.innerHTML=`<b>${esc(p.n)}</b><span>${esc(yrs)||'year unknown'}${p.g!=null?' · gen '+p.g:''}</span>`
      + (p.st?`<span style="color:#8fd3a0">click to open their story →</span>`:`<span style="color:#7e8a99">no story page yet</span>`); }
  tip.style.display='block';
  tip.style.left=Math.min(e.clientX+13, innerWidth-tip.offsetWidth-6)+'px';
  tip.style.top=Math.min(e.clientY+13, innerHeight-tip.offsetHeight-6)+'px';
});
function up(e){ pts.delete(e.pointerId); if(pts.size<2){ lastDist=0; lastMid=null; } }
cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
cv.addEventListener('pointerleave', ()=>{ tip.style.display='none'; lastHover=null; });
cv.addEventListener('click', e => { if (moved) return; const p=hit(e.clientX,e.clientY); if (p && p.st) location.href='story.html#'+encodeURIComponent(p.id); });

// ---- side filter, search, buttons ----
const sidesEl=document.getElementById('sides');
const opts=[['','Both']].concat(SIDE_KEYS.map(k=>[k, SIDE_LABELS[k]]));
function paint(){ sidesEl.innerHTML=opts.map(([v,l])=>`<button data-v="${v}" class="${v===side?'on':''}">${esc(l)}</button>`).join(''); }
sidesEl.addEventListener('click', e => { const b=e.target.closest('button'); if(b){ side=b.dataset.v; paint(); repack(); draw(); } });
const usp=new URLSearchParams(location.search).get('side'); if (SIDE_KEYS.includes(usp)) side=usp;

const qEl=document.getElementById('q');
qEl.addEventListener('input', () => {
  const v=qEl.value.trim().toLowerCase();
  if (v && v.length>=2){ const hitp=PEOPLE.find(p => p.n.toLowerCase().includes(v) && (!side||(p.s&&p.s.includes(side))));
    if (hitp){ const yr=(hitp.b!=null?hitp.b:hitp.d); scaleX=Math.max(scaleX,8); panX=W/2 - yr*scaleX; repack();
      const ln=(LANES.find(p=>p.id===hitp.id)||{})._row||0; panY=H/2 - ln*LH; draw(); } }
});

document.getElementById('reset').addEventListener('click', fitAll);
document.getElementById('zin').addEventListener('click', ()=> zoomAround(W/2,1.5));
document.getElementById('zout').addEventListener('click', ()=> zoomAround(W/2,1/1.5));
document.getElementById('legend').innerHTML =
  `<i style="background:#5b9bd5"></i>${esc(SIDE_LABELS[FK]||'Fernald')} `
  +`<i style="background:#d59a4e;margin-left:8px"></i>${esc(SIDE_LABELS[BK]||'Bagley')} `
  +`<i style="background:#6bbf86;margin-left:8px"></i>both / root`;

paint(); repack(); resize(); fitAll();
window.__tl = { hit, state: () => ({ count: LANES.length, bands: BANDS.length, rows: totalRows, scaleX, panX, panY }) };
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
