"""Build a single self-contained ``family.html`` browser for the whole tree.

Reads the working database directly (structured fields, not the Markdown
packets) and emits one static HTML file under ``data/exports/`` with all data
embedded inline — no separate files to fetch, no internet, no CDN — so it opens
by double-click from ``file://``, renders from a Google Drive mirror, and can be
published as-is to a static (optionally password-protected) website.

Layout is master/detail: a searchable, filterable list of every person on the
left; the selected person's profile, photos, documents, evidence, web findings
and review flags on the right. Photos and documents link to the real image files
by a relative path computed from the exports folder, so the links resolve as
long as the media folder travels with the project (it does in the C:\\Tree
backup and in a published bundle).

    python -m src.build_html_viewer
"""

from __future__ import annotations

import html
import json
import os
from collections import defaultdict
from datetime import date
from urllib.parse import quote

from .ancestral_sides import compute_sides
from .init_database import connect
from .paths import EXPORTS_DIR, WORKING_DB
from .privacy import LIVING_NAME, is_living

OUT_PATH = EXPORTS_DIR / "family.html"

# How confidence_status maps to a colored dot in the UI.
CONFIDENCE_COLORS = {
    "unsourced": "#9aa0a6",
    "gedcom_imported": "#e8a33d",
    "weak_source_only": "#e06c4f",
    "needs_review": "#e8a33d",
}

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _rel(file_path: str) -> str:
    """Relative URL from the exports folder to a media file, web-safe."""
    if not file_path:
        return ""
    rel = os.path.relpath(file_path, EXPORTS_DIR)
    return "/".join(rel.split(os.sep))


def _trim(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def _collect(con, media_base: str = "") -> list[dict]:
    photos: dict[str, list] = defaultdict(list)
    docs: dict[str, list] = defaultdict(list)
    evidence: dict[str, list] = defaultdict(list)
    findings: dict[str, list] = defaultdict(list)
    issues: dict[str, list] = defaultdict(list)
    flagged: dict[str, list] = defaultdict(list)

    def href_for(file_name: str, file_path: str) -> str:
        # R2 (or any) base URL when publishing; relative path for local/Drive viewing.
        return media_base + quote(file_name) if media_base else _rel(file_path)

    for r in con.execute(
        "SELECT l.person_id, m.file_name, m.file_path, m.kind, m.ocr_status, m.ocr_text, "
        "       m.caption, l.link_type "
        "FROM media_person_link l JOIN media_object m ON m.media_id = l.media_id"
    ):
        pid = r["person_id"]
        if r["link_type"] == "review_false_match":
            flagged[pid].append(r["file_name"])
            continue
        item = {"name": r["file_name"], "href": href_for(r["file_name"], r["file_path"]), "caption": r["caption"] or ""}
        if r["kind"] == "document":
            txt = (r["ocr_text"] or "").strip() if r["ocr_status"] in ("done", "vision") else ""
            item["ocr"] = _trim(txt, 500)
            docs[pid].append(item)
        else:
            photos[pid].append(item)

    for r in con.execute(
        "SELECT person_id, source_title, source_site, summary, confidence_label, confidence_score "
        "FROM evidence_candidates ORDER BY confidence_score DESC"
    ):
        evidence[r["person_id"]].append({
            "title": r["source_title"] or "", "site": r["source_site"] or "",
            "summary": _trim(r["summary"], 320), "label": r["confidence_label"] or "",
        })

    for r in con.execute(
        "SELECT person_id, source_title, source_site, claimed_facts, confidence_label, confidence_score "
        "FROM web_research_finding ORDER BY confidence_score DESC"
    ):
        findings[r["person_id"]].append({
            "title": r["source_title"] or "", "site": r["source_site"] or "",
            "facts": _trim(r["claimed_facts"], 260), "label": r["confidence_label"] or "",
        })

    for r in con.execute(
        "SELECT person_id, issue_type, severity, description FROM validation_issue"
    ):
        issues[r["person_id"]].append({
            "type": r["issue_type"], "severity": r["severity"] or "",
            "desc": r["description"] or "",
        })
    for lst in issues.values():
        lst.sort(key=lambda i: SEVERITY_RANK.get(i["severity"], 9))

    people = []
    for p in con.execute(
        "SELECT person_id, full_name, given_name, surname, birth_date, birth_place, "
        "       death_date, death_place, spouse_names, parent_names, generation, "
        "       relationship_to_root, confidence_status FROM people"
    ):
        pid = p["person_id"]
        ph, dc, ev, fi = photos.get(pid, []), docs.get(pid, []), evidence.get(pid, []), findings.get(pid, [])
        fl, iss = flagged.get(pid, []), issues.get(pid, [])
        people.append({
            "id": pid,
            "name": p["full_name"] or "(unknown)",
            "surname": p["surname"] or "",
            "gen": p["generation"],
            "rel": p["relationship_to_root"] or "",
            "conf": p["confidence_status"] or "",
            "born": p["birth_date"] or "", "bornp": p["birth_place"] or "",
            "died": p["death_date"] or "", "diedp": p["death_place"] or "",
            "spouse": p["spouse_names"] or "", "parents": p["parent_names"] or "",
            "photos": ph, "docs": dc, "evidence": ev, "findings": fi,
            "flags": fl, "issues": iss,
            "ev": bool(ph or dc or ev or fi),  # "has evidence" flag for filtering
        })
    # Sort by generation (Nones last) then name, so the list reads top-down.
    people.sort(key=lambda x: (x["gen"] is None, x["gen"] if x["gen"] is not None else 0, x["name"]))
    return people


def _redact(p: dict) -> None:
    p["name"] = LIVING_NAME
    for k in ("born", "bornp", "died", "diedp", "spouse", "parents", "conf"):
        p[k] = ""
    for k in ("photos", "docs", "evidence", "findings", "flags", "issues"):
        p[k] = []
    p["ev"] = False


def build(db_path=WORKING_DB, redact_living: bool = True, media_base: str = "") -> dict:
    with connect(db_path) as con:
        people = _collect(con, media_base)
        sides, side_labels, side_keys = compute_sides(con)
    for p in people:
        p["side"] = sides.get(p["id"], [])
        if redact_living and is_living(p["born"], p["died"], p["gen"]):
            _redact(p)
    payload = json.dumps(people, ensure_ascii=False).replace("</", "<\\/")
    with_ev = sum(1 for p in people if p["ev"])
    generated = date.today().isoformat()
    html_doc = _TEMPLATE.replace("__DATA__", payload) \
        .replace("__TOTAL__", str(len(people))) \
        .replace("__WITHEV__", str(with_ev)) \
        .replace("__DATE__", generated) \
        .replace("__CONF__", json.dumps(CONFIDENCE_COLORS)) \
        .replace("__SIDELABELS__", json.dumps(side_labels)) \
        .replace("__SIDEKEYS__", json.dumps(side_keys))
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    return {"people": len(people), "with_evidence": with_ev, "out": str(OUT_PATH)}


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree</title>
<style>
  :root { --bg:#f7f5f1; --panel:#fff; --line:#e3ddd2; --ink:#2b2b2b; --muted:#6b6b6b; --accent:#7a5c3e; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; color:var(--ink); background:var(--bg); }
  header { background:var(--accent); color:#fff; padding:10px 16px; display:flex; align-items:baseline; gap:14px; }
  header h1 { font-size:18px; margin:0; font-weight:600; }
  header .meta { font-size:13px; opacity:.85; }
  header .root { margin-left:auto; }
  header .root button { background:rgba(255,255,255,.18); color:#fff; border:0; padding:5px 12px; border-radius:5px; cursor:pointer; font-size:13px; }
  .layout { display:flex; height:calc(100vh - 41px); }
  aside { width:340px; min-width:280px; border-right:1px solid var(--line); background:var(--panel); display:flex; flex-direction:column; }
  .filters { padding:10px; border-bottom:1px solid var(--line); display:flex; flex-direction:column; gap:7px; }
  .filters input[type=search], .filters select { width:100%; padding:6px 8px; border:1px solid var(--line); border-radius:5px; font-size:14px; }
  .filters .row { display:flex; gap:7px; }
  .filters label.chk { font-size:13px; color:var(--muted); display:flex; align-items:center; gap:5px; cursor:pointer; }
  #list { overflow:auto; flex:1; }
  .person { padding:7px 12px; border-bottom:1px solid #f0ece4; cursor:pointer; display:flex; align-items:center; gap:8px; }
  .person:hover { background:#faf7f1; }
  .person.sel { background:#efe6d8; }
  .person .dot { width:9px; height:9px; border-radius:50%; flex:none; }
  .person .nm { flex:1; }
  .person .g { font-size:11px; color:var(--muted); flex:none; }
  .person .ic { font-size:11px; flex:none; }
  main { flex:1; overflow:auto; padding:22px 28px; }
  .empty { color:var(--muted); margin-top:40px; text-align:center; }
  h2.name { margin:0 0 2px; font-size:24px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:16px; }
  table.facts { border-collapse:collapse; margin-bottom:8px; }
  table.facts td { padding:3px 14px 3px 0; vertical-align:top; }
  table.facts td.k { color:var(--muted); white-space:nowrap; }
  details { background:var(--panel); border:1px solid var(--line); border-radius:7px; margin:10px 0; padding:4px 12px; }
  details > summary { cursor:pointer; font-weight:600; padding:6px 0; }
  details[data-flag] { border-color:#e0a89a; background:#fdf3f0; }
  details ul { margin:6px 0 10px; padding-left:18px; }
  details li { margin:3px 0; }
  .lab { font-size:11px; background:#efe6d8; color:#6b513a; border-radius:3px; padding:1px 6px; margin-right:5px; }
  .ocr { color:var(--muted); border-left:3px solid var(--line); padding-left:8px; margin:4px 0 0; white-space:pre-wrap; font-size:13px; }
  .sev-critical, .sev-high { color:#b03a26; font-weight:600; }
  a { color:var(--accent); }
  @media (max-width:680px) {
    header { flex-wrap:wrap; gap:6px; }
    header h1 { font-size:16px; }
    .layout { flex-direction:column; height:calc(100vh - 56px); }
    aside { width:auto; border-right:0; border-bottom:1px solid var(--line); }
    #list { max-height:42vh; }
    main { padding:16px; }
  }
  #lb { position:fixed; inset:0; background:rgba(0,0,0,.92); display:none; align-items:center; justify-content:center; z-index:9999; }
  #lb.open { display:flex; }
  #lb img { max-width:96vw; max-height:90vh; object-fit:contain; border-radius:4px; }
  #lbx { position:fixed; top:10px; right:16px; color:#fff; font-size:40px; line-height:1; cursor:pointer; z-index:10000; }
</style>
</head>
<body>
<header>
  <a href="index.html" style="color:#fff;opacity:.8;text-decoration:none;font-size:13px;margin-right:4px">‹ Home</a>
  <h1>Troy Family Tree</h1>
  <span class="meta">__TOTAL__ people · __WITHEV__ with evidence · built __DATE__</span>
  <span class="root"><button id="rootBtn">Root person ▸</button></span>
</header>
<div class="layout">
  <aside>
    <div class="filters">
      <input type="search" id="q" placeholder="Search name…" autocomplete="off">
      <select id="side"></select>
      <div class="row">
        <select id="gen"></select>
        <select id="conf"></select>
      </div>
      <div class="row">
        <label class="chk"><input type="checkbox" id="direct"> Direct line only</label>
        <label class="chk"><input type="checkbox" id="hasev"> Has evidence</label>
      </div>
    </div>
    <div id="list"></div>
  </aside>
  <main id="detail"><div class="empty">Select a person from the list.</div></main>
</div>
<div id="lb"><span id="lbx">×</span><img id="lbimg" alt=""></div>
<script>
const PEOPLE = __DATA__;
const CONF = __CONF__;
const SIDE_LABELS = __SIDELABELS__;
const SIDE_KEYS = __SIDEKEYS__;
const byId = {};
PEOPLE.forEach(p => byId[p.id] = p);

const esc = s => (s==null?"":String(s)).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const dot = c => `<span class="dot" style="background:${CONF[c]||'#c9c2b5'}"></span>`;

// populate generation + confidence filters
const gens = [...new Set(PEOPLE.map(p=>p.gen).filter(g=>g!=null))].sort((a,b)=>a-b);
document.getElementById('gen').innerHTML =
  '<option value="">All generations</option>' + gens.map(g=>`<option value="${g}">Gen ${g}</option>`).join('');
const confs = [...new Set(PEOPLE.map(p=>p.conf).filter(Boolean))].sort();
document.getElementById('conf').innerHTML =
  '<option value="">All confidence</option>' + confs.map(c=>`<option value="${c}">${esc(c)}</option>`).join('');

const sideSel = document.getElementById('side');
sideSel.innerHTML = '<option value="">Both sides</option>' +
  SIDE_KEYS.map(k=>`<option value="${k}">${esc(SIDE_LABELS[k])} side</option>`).join('');
const urlSide = new URLSearchParams(location.search).get('side');
if (urlSide && SIDE_KEYS.includes(urlSide)) sideSel.value = urlSide;

const listEl = document.getElementById('list');
let current = null;

function filtered() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const g = document.getElementById('gen').value;
  const c = document.getElementById('conf').value;
  const direct = document.getElementById('direct').checked;
  const hasev = document.getElementById('hasev').checked;
  const side = document.getElementById('side').value;
  return PEOPLE.filter(p =>
    (!q || p.name.toLowerCase().includes(q)) &&
    (g==="" || String(p.gen)===g) &&
    (!c || p.conf===c) &&
    (!side || (p.side && p.side.includes(side))) &&
    (!direct || /direct/i.test(p.rel)) &&
    (!hasev || p.ev));
}

function renderList() {
  const rows = filtered();
  listEl.innerHTML = rows.map(p => {
    const ic = [p.photos.length?'📷':'', p.docs.length?'📄':'', (p.flags.length||p.issues.length)?'⚠️':''].join('');
    const g = p.gen==null ? '—' : 'g'+p.gen;
    return `<div class="person${p.id===current?' sel':''}" data-id="${esc(p.id)}">
      ${dot(p.conf)}<span class="nm">${esc(p.name)}</span><span class="ic">${ic}</span><span class="g">${g}</span></div>`;
  }).join('') || '<div class="empty">No matches.</div>';
}

function section(title, items, render, opts) {
  if (!items.length) return '';
  const flag = opts && opts.flag ? ' data-flag="1"' : '';
  const open = opts && opts.open ? ' open' : '';
  return `<details${flag}${open}><summary>${esc(title)} (${items.length})</summary><ul>${items.map(render).join('')}</ul></details>`;
}

function renderDetail(p) {
  const facts = [['Born',p.born],['Birthplace',p.bornp],['Died',p.died],['Death place',p.diedp],
                 ['Spouse(s)',p.spouse],['Parents',p.parents],['Confidence',p.conf]]
    .filter(([,v])=>v).map(([k,v])=>`<tr><td class="k">${k}</td><td>${esc(v)}</td></tr>`).join('');
  const sub = [p.gen==null?'Generation —':'Generation '+p.gen, p.rel, p.id].filter(Boolean).map(esc).join(' · ');

  let h = `<h2 class="name">${esc(p.name)}</h2><div class="sub">${sub}</div>`;
  h += `<table class="facts">${facts}</table>`;
  h += section('Photos', p.photos, it =>
        `<li><a href="${esc(it.href)}" class="lb">${esc(it.name)}</a>${it.caption?' — '+esc(it.caption):''}</li>`);
  h += section('Documents', p.docs, it =>
        `<li><a href="${esc(it.href)}" class="lb">${esc(it.name)}</a>${it.ocr?`<div class="ocr">${esc(it.ocr)}</div>`:' <em>(not transcribed)</em>'}</li>`);
  h += section('Evidence', p.evidence, it =>
        `<li><span class="lab">${esc(it.label)}</span><strong>${esc(it.title)}</strong>${it.summary?' — '+esc(it.summary):''}</li>`);
  h += section('Web findings', p.findings, it =>
        `<li><span class="lab">${esc(it.label)}</span>${esc(it.site)}: ${esc(it.facts)}</li>`);
  const review = p.issues.map(i=>`<li class="sev-${esc(i.severity)}">⚠️ [${esc(i.severity)}] ${esc(i.type)}: ${esc(i.desc)}</li>`)
    .concat(p.flags.map(f=>`<li>⚠️ mis-linked document (review): ${esc(f)}</li>`));
  if (review.length) h += `<details data-flag="1" open><summary>Review flags (${review.length})</summary><ul>${review.join('')}</ul></details>`;
  document.getElementById('detail').innerHTML = h;
}

function select(id) {
  current = id; renderDetail(byId[id]);
  document.querySelectorAll('.person').forEach(e=>e.classList.toggle('sel', e.dataset.id===id));
}

listEl.addEventListener('click', e => { const r = e.target.closest('.person'); if (r) select(r.dataset.id); });
['q','gen','conf','side','direct','hasev'].forEach(id =>
  document.getElementById(id).addEventListener('input', renderList));
document.getElementById('rootBtn').addEventListener('click', () => {
  const root = PEOPLE.find(p => p.gen===0) || PEOPLE.find(p => /self|root/i.test(p.rel));
  if (root) { document.getElementById('q').value=''; renderList(); select(root.id);
    document.querySelector('.person.sel')?.scrollIntoView({block:'center'}); }
});

const lb=document.getElementById('lb'), lbimg=document.getElementById('lbimg');
document.getElementById('detail').addEventListener('click', e => {
  const a=e.target.closest('a.lb'); if(!a) return; e.preventDefault();
  lbimg.src=a.getAttribute('href'); lb.classList.add('open');
});
lb.addEventListener('click', e => { if(e.target.id!=='lbimg'){ lb.classList.remove('open'); lbimg.removeAttribute('src'); } });
addEventListener('keydown', e => { if(e.key==='Escape'){ lb.classList.remove('open'); lbimg.removeAttribute('src'); } });

renderList();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
