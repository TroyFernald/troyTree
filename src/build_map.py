"""Build ``map.html`` — a world map of where the family was born and died.

Reads the geocode cache (see ``src.geocode``) and plots one circle per located
place, sized by how many ancestors are tied to it; the popup lists them. Places
not yet geocoded are simply skipped, so the map fills in as the cache grows.
Uses the vendored Leaflet with OpenStreetMap tiles (touch-friendly), a
Fernald/Bagley/Both side filter, and omits living people for privacy.

    python -m src.build_map
"""

from __future__ import annotations

import json

from .ancestral_sides import compute_sides
from .geocode import load_cache, normalize
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import is_living

OUT_PATH = EXPORTS_DIR / "map.html"


def _collect(con, redact_living: bool) -> list[dict]:
    cache = load_cache()
    sides, _, _ = compute_sides(con)
    # place -> {person_id: (name, side_list)}
    places: dict[str, dict] = {}
    for p in con.execute(
        "SELECT person_id, full_name, birth_date, birth_place, death_date, death_place, generation FROM people"
    ):
        if redact_living and is_living(p["birth_date"], p["death_date"], p["generation"]):
            continue
        for col in ("birth_place", "death_place"):
            coords = cache.get(normalize(p[col]))
            if not coords:
                continue
            key = normalize(p[col])
            entry = places.setdefault(key, {"lat": coords[0], "lon": coords[1], "ppl": {}})
            entry["ppl"][p["person_id"]] = (p["full_name"] or "(unknown)", sides.get(p["person_id"], []))

    markers = []
    for place, e in places.items():
        ppl = [{"n": n, "s": s} for (n, s) in e["ppl"].values()]
        ppl.sort(key=lambda x: x["n"])
        markers.append({"place": place, "lat": e["lat"], "lon": e["lon"], "ppl": ppl})
    markers.sort(key=lambda m: -len(m["ppl"]))
    return markers


def build(db_path=WORKING_DB, redact_living: bool = True) -> dict:
    with connect(db_path) as con:
        markers = _collect(con, redact_living)
        _, side_labels, side_keys = compute_sides(con)
    data = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    people_count = sum(len(m["ppl"]) for m in markers)
    html_doc = (
        _TEMPLATE.replace("__DATA__", data)
        .replace("__PLACES__", str(len(markers)))
        .replace("__SIDELABELS__", json.dumps(side_labels))
        .replace("__SIDEKEYS__", json.dumps(side_keys))
    )
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"places": len(markers), "person_place_pins": people_count, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree · World map</title>
<link rel="stylesheet" href="./lib/leaflet.css">
<style>
  html,body { margin:0; height:100%; }
  #map { position:absolute; inset:0; }
  #panel { position:absolute; z-index:1000; top:10px; left:50px; background:rgba(255,255,255,.94);
    border:1px solid #d9cfbf; border-radius:9px; padding:9px 12px; font:14px -apple-system,Segoe UI,Roboto,sans-serif; }
  #panel h1 { font-size:15px; margin:0 0 5px; color:#3a2f25; }
  #panel .meta { color:#8a7866; font-size:12px; margin-bottom:6px; }
  #sides { display:flex; gap:5px; }
  #sides button { font:inherit; font-size:12px; padding:4px 10px; border-radius:14px; cursor:pointer;
    border:1px solid #d9cfbf; background:#fff; color:#3a2f25; }
  #sides button.on { background:#7a5c3e; color:#fff; border-color:#7a5c3e; }
  .leaflet-popup-content { font:13px -apple-system,Segoe UI,Roboto,sans-serif; }
  @media (max-width:600px){ #panel{ left:50px; right:10px; } }
</style>
</head>
<body>
<div id="panel">
  <a href="index.html" style="color:#7a5c3e;text-decoration:none;font-size:12px">‹ Home</a>
  <h1>Where the family lived</h1>
  <div class="meta">__PLACES__ places located · click a marker</div>
  <div id="sides"></div>
</div>
<div id="map"></div>
<script src="./lib/leaflet.js"></script>
<script>
const MARKERS = __DATA__, SIDE_LABELS = __SIDELABELS__, SIDE_KEYS = __SIDEKEYS__;
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

const map = L.map('map', {worldCopyJump:true}).setView([42,-30], 3);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom:18, attribution:'&copy; OpenStreetMap contributors'}).addTo(map);

let side = new URLSearchParams(location.search).get('side') || '';
if (!SIDE_KEYS.includes(side)) side = '';
let layer, firstFit = true;

function render(){
  if (layer) layer.remove();
  layer = L.layerGroup();
  const pts = [];
  for (const m of MARKERS){
    const ppl = side ? m.ppl.filter(p => p.s && p.s.includes(side)) : m.ppl;
    if (!ppl.length) continue;
    const r = Math.min(24, 4 + Math.sqrt(ppl.length)*1.7);
    const names = ppl.slice(0,60).map(p => esc(p.n)).join(', ');
    L.circleMarker([m.lat, m.lon], {radius:r, color:'#5e4630', weight:1, fillColor:'#b07d4f', fillOpacity:.6})
      .bindPopup(`<b>${esc(m.place)}</b><br>${ppl.length} ${ppl.length>1?'people':'person'}<br>`
        + `<span style="color:#6b5a47">${names}${ppl.length>60?' …':''}</span>`)
      .addTo(layer);
    pts.push([m.lat, m.lon]);
  }
  layer.addTo(map);
  if (firstFit && pts.length){ map.fitBounds(pts, {padding:[50,50], maxZoom:6}); firstFit = false; }
}

const sidesEl = document.getElementById('sides');
const opts = [['','Both']].concat(SIDE_KEYS.map(k => [k, SIDE_LABELS[k]]));
function paintBtns(){ sidesEl.innerHTML = opts.map(([v,l]) =>
  `<button data-v="${v}" class="${v===side?'on':''}">${esc(l)}</button>`).join(''); }
sidesEl.addEventListener('click', e => { const b=e.target.closest('button'); if(b){ side=b.dataset.v; paintBtns(); render(); }});
paintBtns(); render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
