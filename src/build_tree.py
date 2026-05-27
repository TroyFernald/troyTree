"""Build ``tree.html`` — a true direct-line pedigree, point-down.

You sit at the bottom point. Your two parents form a tight couple directly above
you; their parents form couples above them; and so on — only the **direct line**
(no siblings, aunts, or cousins). Each couple is joined by a marriage bar with a
line dropping to their child, and labeled by relation ("Your parents", "Your
grandparents", "Your great-grandparents", …). The whole thing fans upward and
outward into a point-down triangle.

Every box shows a photo (when we have one), the name, and the dates, with a
notable-ancestor ★ badge where it applies. Drawn on a single <canvas> with
semantic zoom so panning/zooming stays silky across the full ~2,800-person,
19-generation tree. Click a box to open that person's story. Living people are
redacted.

    python -m src.build_tree [max_gen]
"""

from __future__ import annotations

import json
import sys
from urllib.parse import quote

from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import LIVING_NAME, is_living

OUT_PATH = EXPORTS_DIR / "tree.html"
MAX_GEN = 25  # effectively "all"; the upward walk stops when parent links run out


def _collect(con, max_gen: int, redact_living: bool, media_base: str) -> tuple[list[dict], int]:
    root = con.execute("SELECT person_id FROM people WHERE generation = 0").fetchone()
    if root is None:
        raise SystemExit("No root person (generation 0) found.")
    info = {
        r["person_id"]: r
        for r in con.execute(
            "SELECT person_id, full_name, given_name, surname, birth_date, death_date FROM people"
        )
    }

    # one representative photo per person (lowest media_id), as a resolvable URL
    def href(name, path):
        if media_base:
            return media_base + quote(name)
        import os
        return "/".join(os.path.relpath(path, EXPORTS_DIR).split(os.sep))

    photo: dict[str, str] = {}
    for r in con.execute(
        "SELECT l.person_id, m.file_name, m.file_path FROM media_person_link l "
        "JOIN media_object m ON m.media_id = l.media_id "
        "WHERE m.kind = 'photo' AND l.link_type != 'review_false_match' "
        "ORDER BY m.media_id"
    ):
        photo.setdefault(r["person_id"], href(r["file_name"], r["file_path"]))

    notable: dict[str, str] = {}
    for r in con.execute("SELECT person_id, category FROM notable_person_candidate"):
        notable.setdefault(r["person_id"], r["category"] or "Notable")

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
        living = redact_living and is_living(rec["birth_date"], rec["death_date"], gen)
        if living:
            node = {"id": pid, "gen": gen, "slot": slot, "name": LIVING_NAME, "born": "", "died": ""}
        else:
            node = {
                "id": pid,
                "gen": gen,
                "slot": slot,
                "name": rec["full_name"] or "(unknown)",
                "born": rec["birth_date"] or "",
                "died": rec["death_date"] or "",
            }
            node["given"] = rec["given_name"] or ""
            node["surname"] = rec["surname"] or ""
            if pid in photo:
                node["photo"] = photo[pid]
            if pid in notable:
                node["notable"] = notable[pid]
        slots.append(node)
        if gen < max_gen:
            for i, par in enumerate(parents_of(pid)):
                frontier.append((par, gen + 1, slot * 2 + i))
    return slots, deepest


def build(db_path=WORKING_DB, max_gen: int = MAX_GEN, redact_living: bool = True,
          media_base: str = "") -> dict:
    with connect(db_path) as con:
        slots, deepest = _collect(con, max_gen, redact_living, media_base)
    data = json.dumps(slots, ensure_ascii=False).replace("</", "<\\/")
    html_doc = (
        _TEMPLATE.replace("__DATA__", data)
        .replace("__MAXGEN__", str(max(deepest, 1)))
        .replace("__COUNT__", str(len(slots)))
    )
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"ancestors": len(slots), "generations": deepest, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Troy Family Tree · Pedigree</title>
<style>
  html,body { margin:0; height:100%; background:#2b2b2b; color:#e8e8e8; overflow:hidden;
    font:14px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  #cv { position:fixed; inset:0; display:block; touch-action:none; cursor:grab; }
  #cv:active { cursor:grabbing; }
  #panel { position:fixed; z-index:10; top:10px; left:10px; background:rgba(20,24,32,.86);
    border:1px solid #3a3a3a; border-radius:9px; padding:10px 13px; backdrop-filter:blur(4px); max-width:62vw; }
  #panel h1 { font-size:15px; margin:0 0 3px; }
  #panel .meta { color:#9aa3ad; font-size:11.5px; }
  #panel button { background:#3a3f47; color:#e0e4ea; border:1px solid #4a4f57; border-radius:6px;
    padding:5px 10px; font-size:12px; cursor:pointer; }
  #tip { position:fixed; z-index:20; pointer-events:none; background:rgba(10,12,17,.96);
    border:1px solid #4a4f57; border-radius:6px; padding:6px 9px; font-size:12.5px; display:none; max-width:240px; }
  #tip b { display:block; }
  #tip span { display:block; color:#9aa6b5; }
  #tip .go { color:#8fd3a0; }
</style>
</head>
<body>
<canvas id="cv"></canvas>
<div id="panel">
  <a href="index.html" style="color:#9aa3ad;text-decoration:none;font-size:12px">‹ Home</a>
  <h1>Family tree</h1>
  <div class="meta">__COUNT__ direct ancestors · __MAXGEN__ generations<br>you're at the bottom; each couple is bracketed above their child<br>click a box to open their story · scroll / pinch to zoom · drag to pan</div>
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
const SLOTS = __DATA__, MAXGEN = Math.max(1, __MAXGEN__);
const BW = 84, BH = 116, RAD = 6;   // narrow vertical card: photo on top, name stacked
const COUPLE_GAP = 5;      // space between the two partners of one couple (nearly touching)
const FAMILY_GAP = 16;     // space between different family couples in a row
const ROWH = 150;          // vertical distance between generations
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const MALE = '#5b7fa6', FEMALE = '#b06b54', UNK = '#6f7886';   // box tints (by couple slot, best-effort)
const tint = s => s.gen===0 ? '#55607a' : ((s.slot & 1) ? FEMALE : MALE);

function relation(g){
  if (g===0) return 'You';
  if (g===1) return 'Your parents';
  if (g===2) return 'Your grandparents';
  if (g===3) return 'Your great-grandparents';
  return 'Your ' + (g-2) + '× great-grandparents';
}

// ---- tidy ancestor-tree layout ---------------------------------------------
// Each person's two parents go up and out to the sides (father over his ancestry
// on the left, mother over hers on the right); every family gets its own slice of
// width, so the connector lines never cross. The child sits at the midpoint of its
// two parents, so the chart is a clean point-down triangle.
const byKey = new Map(); SLOTS.forEach(s => byKey.set(s.gen+':'+s.slot, s));
function parentsOf(s){ const r=[]; const a=byKey.get((s.gen+1)+':'+(s.slot*2)); const b=byKey.get((s.gen+1)+':'+(s.slot*2+1)); if(a)r.push(a); if(b)r.push(b); return r; }
const ROOT = byKey.get('0:0');

const LEAFW = BW + FAMILY_GAP;     // horizontal slot for one line's oldest ancestor
function calcWidth(s){             // width this person's whole ancestry needs
  const ps = parentsOf(s);
  if (ps.length === 0) return s.w = LEAFW;
  if (ps.length === 1) return s.w = calcWidth(ps[0]);
  return s.w = calcWidth(ps[0]) + calcWidth(ps[1]);
}
function assignX(s, leftEdge){     // place ancestry across [leftEdge, leftEdge+w], child at parents' midpoint
  const ps = parentsOf(s);
  s.Y = -s.gen * ROWH;
  if (ps.length === 0){ s.X = leftEdge + s.w/2; }
  else if (ps.length === 1){ assignX(ps[0], leftEdge); s.X = ps[0].X; }
  else {
    assignX(ps[0], leftEdge);
    assignX(ps[1], leftEdge + ps[0].w);
    s.X = (ps[0].X + ps[1].X) / 2;
  }
}
calcWidth(ROOT); assignX(ROOT, -ROOT.w/2);
let minX=Infinity, maxX=-Infinity, minY=Infinity, maxY=-Infinity;
for (const s of SLOTS){ if(s.X==null) continue; if(s.X<minX)minX=s.X; if(s.X>maxX)maxX=s.X; if(s.Y<minY)minY=s.Y; if(s.Y>maxY)maxY=s.Y; }

const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
const dpr = Math.min(window.devicePixelRatio||1, 2);
let view = {k:1, x:0, y:0}, W=0, H=0, _raf=0;
const imgs = new Map();
const tip = document.getElementById('tip');

function resize(){ W=innerWidth; H=innerHeight; cv.width=W*dpr; cv.height=H*dpr; cv.style.width=W+'px'; cv.style.height=H+'px'; draw(); }
function getImg(url){ let im=imgs.get(url); if(im===undefined){ im=new Image(); im.onload=schedule; im.onerror=()=>imgs.set(url,null); im.src=url; imgs.set(url,im);} return im; }
function roundRect(x,y,w,h,r){ ctx.beginPath(); ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r); ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath(); }
function fit(txt,w){ if(ctx.measureText(txt).width<=w) return txt; let t=txt; while(t.length>1 && ctx.measureText(t+'…').width>w) t=t.slice(0,-1); return t+'…'; }

function draw(){
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,W,H);
  ctx.save();
  ctx.translate(view.x, view.y); ctx.scale(view.k, view.k);

  // connectors: child rises to a bar that spans up to its two parents (up and out to
  // the sides); each parent drops to the bar. Families never share space, so no crossing.
  ctx.strokeStyle = 'rgba(175,190,210,.6)'; ctx.lineWidth = Math.max(0.7, 1.4/view.k);
  const detail = BH*view.k > 64, mid = BH*view.k > 26;
  for (const s of SLOTS){
    const ps = parentsOf(s); if (!ps.length) continue;
    const childTop = s.Y - BH/2, barY = ps[0].Y + BH/2 + (ROWH-BH)*0.55;
    ctx.beginPath(); ctx.moveTo(s.X, childTop); ctx.lineTo(s.X, barY);   // child up to the bar
    if (ps.length === 2){
      ctx.moveTo(ps[0].X, barY); ctx.lineTo(ps[1].X, barY);             // bar spanning both parents
      ctx.moveTo(ps[0].X, barY); ctx.lineTo(ps[0].X, ps[0].Y + BH/2);   // father drops to the bar (up-left)
      ctx.moveTo(ps[1].X, barY); ctx.lineTo(ps[1].X, ps[1].Y + BH/2);   // mother drops to the bar (up-right)
    } else {
      ctx.lineTo(ps[0].X, barY); ctx.lineTo(ps[0].X, ps[0].Y + BH/2);
    }
    ctx.stroke();
    if (detail){                                                         // relation label under the bar
      ctx.fillStyle = 'rgba(185,196,210,.8)'; ctx.font = '600 10px Segoe UI, sans-serif'; ctx.textAlign = 'center';
      ctx.fillText(relation(ps[0].gen), s.X, barY - 4); ctx.textAlign = 'left';
    }
  }

  // boxes: vertical cards — photo on top, given name over surname, then dates
  ctx.textAlign = 'center';
  for (const s of SLOTS){
    const x = s.X - BW/2, y = s.Y - BH/2, cx = s.X;
    roundRect(x, y, BW, BH, RAD);
    ctx.fillStyle = '#1c2026'; ctx.fill();
    ctx.lineWidth = Math.max(0.5, 2/view.k); ctx.strokeStyle = tint(s); ctx.stroke();   // colored frame
    if (!mid) continue;
    let top;
    if (detail){
      const ph = 56, px = cx - ph/2, py = y + 9;
      if (s.photo){ const im = getImg(s.photo);
        if (im){ ctx.save(); roundRect(px,py,ph,ph,5); ctx.clip(); try{ ctx.drawImage(im,px,py,ph,ph);}catch(e){} ctx.restore(); }
        else { ctx.fillStyle = tint(s); roundRect(px,py,ph,ph,5); ctx.fill(); } }
      else { ctx.fillStyle = '#262b33'; roundRect(px,py,ph,ph,5); ctx.fill(); }
      top = py + ph + 15;
    } else { top = y + BH*0.46; }
    const g1 = s.given || s.name;
    ctx.fillStyle = '#eef1f5'; ctx.font = '700 11px Segoe UI, sans-serif';
    ctx.fillText(fit(g1, BW-12), cx, top);
    if (s.given && s.surname){ ctx.fillText(fit(s.surname, BW-12), cx, top + 14); }
    if (detail){
      const dates = [s.born, s.died].filter(Boolean).join(' – ');
      if (dates){ ctx.font = '10px Segoe UI, sans-serif'; ctx.fillStyle = '#aab4c2';
        ctx.fillText(fit(dates, BW-8), cx, top + ((s.given&&s.surname)?30:16)); }
    }
    if (s.notable){ ctx.font='12px Segoe UI, sans-serif'; ctx.fillStyle='#e6c06a';
      ctx.textAlign='right'; ctx.fillText('★', x+BW-6, y+15); ctx.textAlign='center'; }
  }
  ctx.textAlign = 'left';
  ctx.restore();
}
function schedule(){ if(_raf) return; _raf=requestAnimationFrame(()=>{ _raf=0; draw(); }); }

// ---- framing ----
// default: fit all generations vertically, you centered at the bottom; the chart
// is far wider than tall, so pan left/right to follow a branch
function frameRoot(){ view.k = Math.min(1.0, (H-90)/((MAXGEN+1)*ROWH));
  view.x = W/2 - ROOT.X*view.k; view.y = (H-60) - ROOT.Y*view.k; draw(); }
function fitAll(){ const w=(maxX-minX)+BW+60, h=(maxY-minY)+BH+80;
  view.k = Math.min(W/w, H/h, 1.1);
  view.x = W/2 - ((minX+maxX)/2)*view.k; view.y = H/2 - ((minY+maxY)/2)*view.k; draw(); }
function zoomAround(cx,cy,f){ view.x=cx-(cx-view.x)*f; view.y=cy-(cy-view.y)*f; view.k*=f; schedule(); }

// ---- hit testing ----
function nodeAt(px,py){
  const wx=(px-view.x)/view.k, wy=(py-view.y)/view.k;
  for (const s of SLOTS){ if (Math.abs(wx-s.X)<=BW/2 && Math.abs(wy-s.Y)<=BH/2) return s; }
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
    else if (pts.size===2){ const [a,b]=[...pts.values()]; const d=Math.hypot(a.x-b.x,a.y-b.y); const m={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
      if (lastDist){ zoomAround(m.x,m.y,d/lastDist); if(lastMid){ view.x+=m.x-lastMid.x; view.y+=m.y-lastMid.y; schedule(); } }
      lastDist=d; lastMid=m; }
    return;
  }
  const s=nodeAt(e.clientX,e.clientY);
  if (!s){ tip.style.display='none'; lastHover=null; return; }
  if (s!==lastHover){ lastHover=s;
    const dates=[s.born,s.died].filter(Boolean).join(' – ');
    tip.innerHTML = `<b>${esc(s.name)}</b><span>${esc(relation(s.gen))}${dates?' · '+esc(dates):''}</span>`
      + (s.notable?`<span style="color:#e6c06a">★ ${esc(s.notable)}</span>`:'')
      + (s.id&&s.name!=='Living'?`<span class="go">click to open their story →</span>`:''); }
  tip.style.display='block';
  tip.style.left=Math.min(e.clientX+12, innerWidth-tip.offsetWidth-6)+'px';
  tip.style.top=Math.min(e.clientY+12, innerHeight-tip.offsetHeight-6)+'px';
});
function up(e){ pts.delete(e.pointerId); if(pts.size<2){ lastDist=0; lastMid=null; } }
cv.addEventListener('pointerup', up); cv.addEventListener('pointercancel', up);
cv.addEventListener('pointerleave', ()=>{ tip.style.display='none'; lastHover=null; });
cv.addEventListener('click', e => { if (moved) return; const s=nodeAt(e.clientX,e.clientY);
  if (s && s.id && s.name!=='Living') location.href='story.html#'+encodeURIComponent(s.id); });

document.getElementById('reset').addEventListener('click', frameRoot);
document.getElementById('all').addEventListener('click', fitAll);
document.getElementById('zin').addEventListener('click', ()=> zoomAround(W/2,H/2,1.5));
document.getElementById('zout').addEventListener('click', ()=> zoomAround(W/2,H/2,1/1.5));

// headless-test hook (see tools/test_tree.js)
window.__tree = {
  state: () => ({ k:view.k, x:view.x, y:view.y, nodes:SLOTS.length, rootX:ROOT.X }),
  hit: (x,y) => { const s=nodeAt(x,y); return s ? {id:s.id, gen:s.gen, name:s.name, X:Math.round(s.X), notable:!!s.notable, photo:!!s.photo} : null; },
  parentsX: () => { const p=parentsOf(ROOT).map(s=>Math.round(s.X)); return {root:Math.round(ROOT.X), parents:p}; },
  frameRoot, fitAll
};

resize(); frameRoot();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    mg = int(sys.argv[1]) if len(sys.argv) > 1 else MAX_GEN
    print(build(max_gen=mg))
