"""Build ``story.html`` — a book of the family with page-turn animation.

Each ancestor (and anyone with photos, evidence, findings, or a newspaper
mention) is a richly laid-out page: a narrative written from their facts, a lead
portrait, an "In the newspapers" section pulling verified historic-newspaper
hits, a "Records & sources" list, and a photo gallery. Pages turn with a hinged
flip animation (arrows, swipe, or the searchable table of contents).

Neutral phrasing throughout (no recorded sex), living people redacted by
default, photos served from the R2 ``media_base`` when publishing.

    python -m src.build_storybook
"""

from __future__ import annotations

import json
from collections import defaultdict
from urllib.parse import quote

from .ancestral_sides import compute_sides
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import LIVING_NAME, is_living

OUT_PATH = EXPORTS_DIR / "story.html"
NEWS_FILTER = "lower(source_type) LIKE '%newspaper%' OR lower(source_site) LIKE '%chronic%'"
MIL_FILTER = (
    "lower(claimed_facts) LIKE '%regiment%' OR lower(claimed_facts) LIKE '%militia%' "
    "OR lower(claimed_facts) LIKE '%pension%' OR lower(claimed_facts) LIKE '%soldier%' "
    "OR lower(claimed_facts) LIKE '%private%' OR lower(claimed_facts) LIKE '%corporal%' "
    "OR lower(claimed_facts) LIKE '%enlist%' OR lower(claimed_facts) LIKE '%muster%' "
    "OR lower(claimed_facts) LIKE '%infantry%' OR lower(claimed_facts) LIKE '%cavalry%' "
    "OR lower(claimed_facts) LIKE '%matross%' OR lower(claimed_facts) LIKE '%revolutionary war%' "
    "OR lower(claimed_facts) LIKE '%civil war%' OR lower(source_title) LIKE '%dar%'"
)

# Verified public-domain portraits + castle images (Wikimedia) for the genuinely
# famous historical figures claimed in the tree. Labeled illustrative/unverified
# in the UI. Duplicate person records are mapped to the same imagery.
_COLIGNY2 = {"portrait": "https://upload.wikimedia.org/wikipedia/commons/d/de/Fran%C3%A7ois_Clouet_-_Admiral_Gaspard_II_de_Coligny_-_168-1925_-_Saint_Louis_Art_Museum.jpg",
             "castle": "https://upload.wikimedia.org/wikipedia/commons/2/2d/Ch%C3%A2tillon-Coligny-donjon.jpg",
             "wiki": "https://en.wikipedia.org/wiki/Gaspard_II_de_Coligny",
             "caption": "Admiral of France and Huguenot leader, assassinated in the St. Bartholomew's Day Massacre, 1572 · Château de Châtillon-Coligny"}
_COLIGNY1 = {"portrait": "https://upload.wikimedia.org/wikipedia/commons/7/77/Montmorency_%28Val-d%E2%80%99Oise%29_Saint-Martin77644_-_Gaspard_I_de_Coligny.JPG",
             "castle": "https://upload.wikimedia.org/wikipedia/commons/2/2d/Ch%C3%A2tillon-Coligny-donjon.jpg",
             "wiki": "https://en.wikipedia.org/wiki/Gaspard_I_de_Coligny",
             "caption": "Marshal of France (c.1465-1522), the 'Marshal of Châtillon' · Château de Châtillon-Coligny"}
_BLOIS = "https://upload.wikimedia.org/wikipedia/commons/8/83/Charles-Ca%C3%AFus_Renoux%2C_Chateau_de_Elois.jpg"
NOBLE_IMAGES = {
    "@I322625930211@": _COLIGNY2, "@I322625938153@": _COLIGNY2,
    "@I322625938207@": _COLIGNY1, "@I322625938202@": _COLIGNY1, "@I322625930245@": _COLIGNY1,
    "@I322625938264@": {"portrait": "https://upload.wikimedia.org/wikipedia/commons/b/ba/BNF_-_Latin_9474_-_Jean_Bourdichon_-_Grandes_Heures_d%27Anne_de_Bretagne_-_f._3r_-_Anne_de_Bretagne_entre_trois_saintes_%28d%C3%A9tail%29.jpg",
        "castle": _BLOIS, "wiki": "https://en.wikipedia.org/wiki/Anne_of_Brittany",
        "caption": "Duchess of Brittany and twice Queen consort of France · Château de Blois"},
    "@I322625938260@": {"portrait": "https://upload.wikimedia.org/wikipedia/commons/8/84/Ludwig_XII._von_Frankreich.jpg",
        "castle": _BLOIS, "wiki": "https://en.wikipedia.org/wiki/Louis_XII",
        "caption": "King of France 1498-1515; husband of Anne of Brittany · Château de Blois"},
    "@I322738217959@": {"portrait": "https://upload.wikimedia.org/wikipedia/commons/9/91/Steven_van_der_Meulen_Catherine_Carey_Lady_Knollys.jpg",
        "castle": "", "wiki": "https://en.wikipedia.org/wiki/Catherine_Carey",
        "caption": "Lady Knollys, chief Lady of the Bedchamber to Elizabeth I; daughter of Mary Boleyn"},
}


def _narrate(name, born, bornp, died, diedp, spouse, parents) -> str:
    s = []
    if born and bornp:
        s.append(f"{name} was born {born} in {bornp}.")
    elif born:
        s.append(f"{name} was born {born}.")
    elif bornp:
        s.append(f"{name} was born in {bornp}.")
    else:
        s.append(f"This is {name}.")
    if parents:
        s.append(f"A child of {parents}.")
    if spouse:
        s.append(f"Married {spouse}.")
    if died and diedp:
        s.append(f"Died {died} in {diedp}.")
    elif died:
        s.append(f"Died {died}.")
    elif diedp:
        s.append(f"Died in {diedp}.")
    return " ".join(s)


def noble_images() -> dict:
    """Famous-figure imagery: hardcoded defaults merged with the agent-built
    noble_images.json (portraits, castles, stories) when present."""
    imgs = dict(NOBLE_IMAGES)
    f = EXPORTS_DIR / "noble_images.json"
    if f.exists():
        try:
            for pid, v in json.loads(f.read_text(encoding="utf-8")).items():
                if isinstance(v, dict) and (v.get("portrait") or v.get("castle")):
                    v.setdefault("caption", v.get("story", ""))
                    imgs[pid] = v
        except Exception:
            pass
    return imgs


def deep_dives() -> dict:
    """Curated long-form narratives + verified imagery for marquee ancestors,
    keyed by person_id. Authored in ``data/exports/deep_dives.json``; rendered as
    a featured story on that person's storybook page."""
    f = EXPORTS_DIR / "deep_dives.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _collect(con, redact_living: bool, media_base: str, ni_map: dict) -> list[dict]:
    def href(file_name, file_path):
        if media_base:
            return media_base + quote(file_name)
        import os
        return "/".join(os.path.relpath(file_path, EXPORTS_DIR).split(os.sep))

    photos = defaultdict(list)
    for r in con.execute(
        "SELECT l.person_id, m.file_name, m.file_path, m.caption FROM media_person_link l "
        "JOIN media_object m ON m.media_id=l.media_id "
        "WHERE m.kind='photo' AND l.link_type!='review_false_match' ORDER BY m.media_id"
    ):
        photos[r["person_id"]].append({"src": href(r["file_name"], r["file_path"]), "cap": r["caption"] or ""})

    papers = defaultdict(list)
    for r in con.execute(
        f"SELECT person_id, source_title, source_url, snippet, claimed_facts, notes "
        f"FROM web_research_finding WHERE {NEWS_FILTER} ORDER BY confidence_score DESC"
    ):
        papers[r["person_id"]].append({
            "title": r["source_title"] or "Newspaper", "url": r["source_url"] or "",
            "when": r["notes"] or "", "text": (r["snippet"] or r["claimed_facts"] or "")[:1600],
        })

    military = defaultdict(list)
    for r in con.execute(
        f"SELECT person_id, source_title, source_site, source_url, claimed_facts, confidence_label "
        f"FROM web_research_finding WHERE ({MIL_FILTER}) AND NOT ({NEWS_FILTER}) ORDER BY confidence_score DESC"
    ):
        military[r["person_id"]].append({
            "site": r["source_site"] or "", "url": r["source_url"] or "",
            "text": (r["claimed_facts"] or "")[:260], "label": r["confidence_label"] or "",
        })

    records = defaultdict(list)
    for r in con.execute(
        f"SELECT person_id, source_title, source_site, claimed_facts, confidence_label "
        f"FROM web_research_finding WHERE NOT ({NEWS_FILTER}) AND NOT ({MIL_FILTER}) "
        f"AND claimed_facts<>'' ORDER BY confidence_score DESC"
    ):
        records[r["person_id"]].append({
            "site": r["source_site"] or "", "title": r["source_title"] or "",
            "text": (r["claimed_facts"] or "")[:240], "label": r["confidence_label"] or "",
        })

    noble = {}
    for r in con.execute(
        "SELECT person_id, notable_reason FROM notable_person_candidate "
        "WHERE category IN ('royal_noble', 'medieval_descent')"
    ):
        noble.setdefault(r["person_id"], r["notable_reason"] or "Claimed noble or royal descent")

    dd_map = deep_dives()
    sides, _, _ = compute_sides(con)
    pages = []
    for p in con.execute(
        "SELECT person_id, full_name, birth_date, birth_place, death_date, death_place, "
        "spouse_names, parent_names, generation, relationship_to_root FROM people"
    ):
        pid = p["person_id"]
        if not (pid in sides or pid in photos or pid in papers or pid in military or pid in records or pid in noble or pid in ni_map):
            continue
        living = redact_living and is_living(p["birth_date"], p["death_date"], p["generation"])
        if living:
            pages.append({"id": pid, "name": LIVING_NAME, "gen": p["generation"], "side": sides.get(pid, []),
                          "text": "Details withheld for a living family member.",
                          "photos": [], "papers": [], "records": [], "facts": []})
            continue
        name = p["full_name"] or "(unknown)"
        facts = [(k, v) for k, v in [
            ("Born", p["birth_date"]), ("Birthplace", p["birth_place"]),
            ("Died", p["death_date"]), ("Death place", p["death_place"]),
            ("Spouse", p["spouse_names"]), ("Parents", p["parent_names"]),
        ] if v]
        pages.append({
            "id": pid, "name": name, "gen": p["generation"], "side": sides.get(pid, []),
            "rel": p["relationship_to_root"] or "",
            "text": _narrate(name, p["birth_date"] or "", p["birth_place"] or "",
                             p["death_date"] or "", p["death_place"] or "",
                             p["spouse_names"] or "", p["parent_names"] or ""),
            "facts": facts,
            "photos": photos.get(pid, []),
            "papers": papers.get(pid, []),
            "military": military.get(pid, [])[:6],
            "records": records.get(pid, [])[:4],
            "noble": noble.get(pid, ""),
            "ni": ni_map.get(pid),
            "dd": dd_map.get(pid),
        })
    pages.sort(key=lambda x: (x["gen"] is None, x["gen"] if x["gen"] is not None else 0, x["name"]))
    return pages


def build(db_path=WORKING_DB, redact_living: bool = True, media_base: str = "") -> dict:
    with connect(db_path) as con:
        pages = _collect(con, redact_living, media_base, noble_images())
        _, side_labels, side_keys = compute_sides(con)
    data = json.dumps(pages, ensure_ascii=False).replace("</", "<\\/")
    html_doc = (_TEMPLATE.replace("__DATA__", data)
                .replace("__SIDELABELS__", json.dumps(side_labels))
                .replace("__SIDEKEYS__", json.dumps(side_keys)))
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    news = sum(len(p["papers"]) for p in pages)
    return {"pages": len(pages), "newspaper_mentions": news, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Troy Family Tree · Storybook</title>
<style>
  :root { --bg:#241c12; --paper:#fbf4e6; --ink:#352a1b; --muted:#8a775c; --accent:#7a5c3e; --rule:#e6d8bf; }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:radial-gradient(circle at 50% 0,#3a2e1d,var(--bg));
    color:var(--ink); font:17px/1.7 Georgia,"Times New Roman",serif; overflow:hidden; }
  #bar { position:fixed; top:10px; left:50%; transform:translateX(-50%); z-index:30; display:flex; gap:10px;
    align-items:center; background:rgba(20,15,9,.78); border:1px solid #4a3d2c; border-radius:24px;
    padding:6px 14px; color:#ecdfc6; font-size:13px; backdrop-filter:blur(4px); }
  #bar a, #bar button { color:#ecdfc6; background:none; border:0; cursor:pointer; font:inherit; text-decoration:none; }
  #bar select { background:#15110b; color:#ecdfc6; border:1px solid #4a3d2c; border-radius:6px; font:inherit; padding:2px 6px; }
  #book { height:100vh; display:flex; align-items:flex-start; justify-content:center; padding:58px 16px 16px; }
  .page { background:var(--paper); width:min(680px,96vw); height:calc(100vh - 74px); max-height:940px; border-radius:6px;
    box-shadow:0 18px 50px rgba(0,0,0,.5); padding:34px 40px; overflow:auto;
    background-image:linear-gradient(90deg,rgba(0,0,0,.07),transparent 5%); position:relative; }
  .page.out-next{animation:flipOutL .26s ease-in forwards}
  .page.in-next{animation:flipInL .28s ease-out forwards}
  .page.out-prev{animation:flipOutR .26s ease-in forwards}
  .page.in-prev{animation:flipInR .28s ease-out forwards}
  @keyframes flipOutL{to{transform:rotateY(-88deg);box-shadow:-26px 0 40px rgba(0,0,0,.4)}}
  @keyframes flipInL{from{transform:rotateY(-88deg)}to{transform:rotateY(0)}}
  @keyframes flipOutR{to{transform:rotateY(88deg);box-shadow:26px 0 40px rgba(0,0,0,.4)}}
  @keyframes flipInR{from{transform:rotateY(88deg)}to{transform:rotateY(0)}}
  .gen { color:var(--muted); font-size:12px; letter-spacing:1px; text-transform:uppercase; }
  h1.nm { font-size:30px; margin:3px 0 14px; line-height:1.1; }
  .lead { width:100%; max-height:46vh; object-fit:contain; background:#efe6d2; border-radius:5px; margin:0 0 16px;
    box-shadow:0 3px 12px rgba(0,0,0,.2); }
  .body { margin:0 0 18px; }
  .facts { font-size:14px; color:#5b4a35; border-top:1px solid var(--rule); border-bottom:1px solid var(--rule);
    padding:10px 0; margin:0 0 18px; columns:2; }
  .facts div { break-inside:avoid; margin:2px 0; }
  .facts b { color:var(--muted); font-weight:600; }
  .crest { text-align:center; margin:0 0 16px; padding:12px 14px; border:2px solid #b89455; border-radius:8px;
    background:linear-gradient(180deg,#f7eccb,#f0e0bc); color:#6b4f25; font-size:15px; letter-spacing:1px;
    box-shadow:inset 0 0 0 1px #e8d39e; }
  .crest span { display:block; font-size:12.5px; letter-spacing:0; font-style:italic; color:#8a6a38; margin-top:4px; }
  .portraits { display:flex; gap:12px; flex-wrap:wrap; margin:0 0 8px; }
  .portraits figure { margin:0; flex:1; min-width:140px; }
  .portraits img { width:100%; max-height:340px; object-fit:contain; background:#efe6d2; border-radius:5px; box-shadow:0 3px 12px rgba(0,0,0,.28); }
  .portraits figcaption { font-size:11.5px; color:#8a775c; font-style:italic; text-align:center; margin-top:3px; }
  .nicap { font-size:13.5px; color:#5b4a35; margin:0 0 14px; }
  .dd-badge { display:inline-block; background:linear-gradient(180deg,#f7eccb,#f0e0bc); border:1px solid #d8c08a;
    color:#6b4f25; font-size:12px; letter-spacing:1.5px; text-transform:uppercase; padding:4px 13px; border-radius:20px; margin:0 0 14px; }
  .dd-narr p { margin:0 0 13px; font-size:17px; }
  .dd-narr p:first-letter { font-size:2.2em; line-height:.8; float:left; padding:6px 7px 0 0; color:var(--accent); font-weight:bold; }
  .portraits figcaption .cr { display:block; color:#a18a63; font-size:10.5px; font-style:normal; margin-top:1px; }
  .dd-src { font-size:12.5px; color:var(--muted); border-top:1px solid var(--rule); margin-top:20px; padding-top:8px; }
  .dd-src a { color:var(--accent); } .dd-src b { color:var(--accent); font-weight:600; }
  h2.sec { font-size:14px; letter-spacing:1px; text-transform:uppercase; color:var(--accent);
    border-bottom:2px solid var(--accent); padding-bottom:3px; margin:22px 0 10px; }
  .clip { background:#f3ead4; border:1px solid #ddcba6; border-left:4px solid #b08949; padding:10px 13px;
    margin:8px 0; font-size:15px; }
  .clip .src { display:block; font-size:12px; color:var(--muted); margin-top:5px; font-style:italic; }
  .rec { font-size:14.5px; margin:7px 0; }
  .rec .tag { font-size:11px; background:#efe2c7; color:#6b513a; border-radius:3px; padding:1px 6px; margin-right:6px; }
  .gallery { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
  .gallery img { width:108px; height:108px; object-fit:contain; background:#efe6d2; border-radius:4px; box-shadow:0 2px 6px rgba(0,0,0,.18); }
  .nav { position:fixed; top:50%; transform:translateY(-50%); width:56px; height:56px; border:0;
    background:rgba(20,15,9,.6); color:#ecdfc6; cursor:pointer; font-size:30px; z-index:20;
    border-radius:50%; display:flex; align-items:center; justify-content:center;
    box-shadow:0 3px 12px rgba(0,0,0,.45); transition:background .15s; }
  .nav:hover { background:rgba(122,92,62,.95); }
  #prev{left:16px} #next{right:16px}
  #toc { position:fixed; top:0; left:0; bottom:0; width:300px; max-width:84vw; background:#1f1810; color:#ecdfc6;
    transform:translateX(-100%); transition:transform .2s; z-index:40; display:flex; flex-direction:column; }
  #toc.open{transform:none}
  #toc input{margin:12px;padding:8px;border-radius:6px;border:1px solid #4a3d2c;background:#15110b;color:#ecdfc6}
  #tocList{overflow:auto;flex:1}
  #tocList div{padding:7px 14px;cursor:pointer;font-size:14px;border-bottom:1px solid #2c2418}
  #tocList div:hover{background:#2c2418}
  @media (max-width:600px){
    #bar{flex-wrap:wrap; max-width:94vw; justify-content:center; row-gap:5px; font-size:12px}
    #book{padding:78px 8px 18px}
    .page{padding:22px 18px; width:96vw; height:82vh}
    .facts{columns:1}
    .nav{width:48px; height:48px; font-size:26px}
    #prev{left:8px} #next{right:8px}
    .gallery img{width:84px; height:84px}
  }
  .lead, .gallery img, .portraits img { cursor:zoom-in; }
  #lb{position:fixed;inset:0;background:rgba(0,0,0,.93);display:none;align-items:center;justify-content:center;z-index:9999;}
  #lb.open{display:flex;}
  #lb img{max-width:96vw;max-height:90vh;object-fit:contain;border-radius:4px;}
  #lbx{position:fixed;top:10px;right:16px;color:#fff;font-size:40px;line-height:1;cursor:pointer;z-index:10000;}
</style>
</head>
<body>
<div id="bar">
  <a href="index.html">‹ Home</a>
  <button id="toc-btn">☰ Contents</button>
  <select id="side"></select>
  <span id="count"></span>
</div>
<aside id="toc"><input id="tocq" placeholder="Search…" autocomplete="off"><div id="tocList"></div></aside>
<div id="book"><div class="page" id="page"></div></div>
<div id="lb"><span id="lbx">×</span><img id="lbimg" alt=""></div>
<button class="nav" id="prev">‹</button>
<button class="nav" id="next">›</button>
<script>
const PAGES=__DATA__, SIDE_LABELS=__SIDELABELS__, SIDE_KEYS=__SIDEKEYS__;
const esc=s=>(s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let view=PAGES, idx=0, animating=false;

const sideSel=document.getElementById('side');
sideSel.innerHTML='<option value="">Both sides</option>'+SIDE_KEYS.map(k=>`<option value="${k}">${esc(SIDE_LABELS[k])} side</option>`).join('');
const usp=new URLSearchParams(location.search).get('side');
if(usp&&SIDE_KEYS.includes(usp)) sideSel.value=usp;

function html(p){
  if(!p) return '<p>No pages for this side.</p>';
  let h=`<div class="gen">${p.gen==null?'':'Generation '+p.gen}${p.rel?' · '+esc(p.rel):''}</div><h1 class="nm">${esc(p.name)}</h1>`;
  if(p.dd){ const dd=p.dd;
    if(dd.tag==='legend') h+=`<div class="crest">🏰 ⚜ <b>Family legend</b> ⚜ 🏰<span>A claimed royal/noble ancestor — unproven through the colonial bridge. A wonderful story to chase, not established fact.</span></div>`;
    else h+=`<div class="dd-badge">📜 Featured life story</div>`;
    if(dd.images&&dd.images.length) h+=`<div class="portraits">`+dd.images.map(im=>
      `<figure><img src="${esc(im.url)}" alt="" onerror="this.parentNode.style.display='none'"><figcaption>${esc(im.caption||'')}${im.credit?`<span class="cr">${esc(im.credit)}</span>`:''}</figcaption></figure>`).join('')+`</div>`;
    h+=`<div class="dd-narr">`+(dd.narrative||[]).map(par=>`<p>${esc(par)}</p>`).join('')+`</div>`;
  } else {
    if(p.noble) h+=`<div class="crest">🏰 ⚜ <b>Claimed noble line</b> ⚜ 🏰<span>Family legend — ${esc(p.noble)}. Unproven through the colonial bridge; treat as lore, not fact.</span></div>`;
    if(p.ni){ const ni=p.ni; let pf='';
      if(ni.portrait) pf+=`<figure><img src="${esc(ni.portrait)}" alt="" onerror="this.parentNode.style.display='none'"><figcaption>Illustrative portrait — claimed &amp; unverified</figcaption></figure>`;
      if(ni.castle) pf+=`<figure><img src="${esc(ni.castle)}" alt="" onerror="this.parentNode.style.display='none'"><figcaption>🏰 ${ni.castle_name?esc(ni.castle_name):'Family seat'}</figcaption></figure>`;
      if(pf) h+=`<div class="portraits">${pf}</div>`;
      const story=ni.story||ni.caption||'';
      if(story) h+=`<p class="nicap">${esc(story)}${ni.wiki?` · <a href="${esc(ni.wiki)}" target="_blank">Wikipedia ↗</a>`:''}</p>`; }
    if(p.photos&&p.photos.length) h+=`<img class="lead" src="${esc(p.photos[0].src)}" alt="" onerror="this.style.display='none'">`;
    h+=`<p class="body">${esc(p.text)}</p>`;
  }
  if(p.facts&&p.facts.length) h+=`<div class="facts">`+p.facts.map(f=>`<div><b>${esc(f[0])}:</b> ${esc(f[1])}</div>`).join('')+`</div>`;
  if(p.papers&&p.papers.length){
    h+=`<h2 class="sec">In the newspapers</h2>`+p.papers.map(n=>
      `<div class="clip">${esc(n.text)}${n.url?` <a href="${esc(n.url)}" target="_blank">↗</a>`:''}<span class="src">${esc(n.title)}${n.when?' — '+esc(n.when):''}</span></div>`).join('');
  }
  if(p.military&&p.military.length){
    h+=`<h2 class="sec">⚔ Military service</h2>`+p.military.map(m=>
      `<div class="rec"><span class="tag">${esc(m.label)}</span>${esc(m.text)}${m.url?` <a href="${esc(m.url)}" target="_blank">↗</a>`:''} <span style="color:#8a775c">— ${esc(m.site)}</span></div>`).join('');
  }
  if(p.records&&p.records.length){
    h+=`<h2 class="sec">Records & sources</h2>`+p.records.map(r=>
      `<div class="rec"><span class="tag">${esc(r.label)}</span>${esc(r.text)} <span style="color:#8a775c">— ${esc(r.site||r.title)}</span></div>`).join('');
  }
  if(p.photos&&p.photos.length>1){
    h+=`<h2 class="sec">Photographs (${p.photos.length})</h2><div class="gallery">`+
      p.photos.map(ph=>`<img src="${esc(ph.src)}" title="${esc(ph.cap)}" alt="" onerror="this.style.display='none'">`).join('')+`</div>`;
  }
  if(p.dd&&p.dd.sources&&p.dd.sources.length){
    h+=`<div class="dd-src"><b>Sources:</b> `+p.dd.sources.map(s=>s.url?`<a href="${esc(s.url)}" target="_blank">${esc(s.title)} ↗</a>`:esc(s.title)).join(' · ')+`</div>`;
  }
  return h;
}
const pageEl=document.getElementById('page');
function render(){
  pageEl.innerHTML=html(view[idx]); pageEl.scrollTop=0;
  document.getElementById('count').textContent=view.length?`${idx+1} / ${view.length}`:'';
}
function go(d){
  const ni=Math.max(0,Math.min(view.length-1,idx+d));
  if(ni===idx) return;
  idx=ni; render();
}
function applySide(){
  const s=sideSel.value;
  view=s?PAGES.filter(p=>p.side&&p.side.includes(s)):PAGES;
  idx=0; render(); buildTOC();
}
document.getElementById('next').onclick=()=>go(1);
document.getElementById('prev').onclick=()=>go(-1);
addEventListener('keydown',e=>{if(e.key==='ArrowRight')go(1);if(e.key==='ArrowLeft')go(-1);});
sideSel.onchange=applySide;
let sx=0; const book=document.getElementById('book');
book.addEventListener('touchstart',e=>sx=e.touches[0].clientX,{passive:true});
book.addEventListener('touchend',e=>{const dx=e.changedTouches[0].clientX-sx; if(Math.abs(dx)>50)go(dx<0?1:-1);});
const lb=document.getElementById('lb'),lbimg=document.getElementById('lbimg');
pageEl.addEventListener('click',e=>{ if(e.target.tagName==='IMG'&&e.target.src){ lbimg.src=e.target.src; lb.classList.add('open'); }});
lb.addEventListener('click',e=>{ if(e.target.id!=='lbimg'){ lb.classList.remove('open'); lbimg.removeAttribute('src'); }});
addEventListener('keydown',e=>{ if(e.key==='Escape'){ lb.classList.remove('open'); lbimg.removeAttribute('src'); }});
const toc=document.getElementById('toc'), tocList=document.getElementById('tocList');
document.getElementById('toc-btn').onclick=()=>toc.classList.toggle('open');
function buildTOC(f=''){f=f.toLowerCase();
  tocList.innerHTML=view.map((p,i)=>(!f||p.name.toLowerCase().includes(f))?`<div data-i="${i}">${p.dd?'📜 ':''}${esc(p.name)} <span style="color:#8a775c">${p.gen==null?'':'· g'+p.gen}</span></div>`:'').join('');}
tocList.onclick=e=>{const d=e.target.closest('div'); if(d){idx=+d.dataset.i; render(); toc.classList.remove('open');}};
document.getElementById('tocq').oninput=e=>buildTOC(e.target.value);
applySide();
function gotoHash(){
  const key=decodeURIComponent((location.hash||'').slice(1)); if(!key) return;
  const match=p=>p.id===key||p.name===key;
  let i=view.findIndex(match);
  if(i<0){ sideSel.value=''; applySide(); i=view.findIndex(match); }
  if(i>=0){ idx=i; render(); }
}
addEventListener('hashchange',gotoHash); gotoHash();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
