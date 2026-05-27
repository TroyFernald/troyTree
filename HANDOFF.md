# Troy Family Tree — Project Handoff

This project turns an Ancestry GEDCOM export into (1) a curated **research database**,
(2) a private, password-protected **family-heritage website**, and (3) a read-only
**MCP server** so an AI assistant can answer questions about the family.

Three layers, one repo:

- **Research/evidence pipeline** — `src/*.py` import the GEDCOM into
  `data/working/research.sqlite`, normalize sources, audit direct ancestors, detect
  duplicates/validation issues, generate public-web research worklists, ingest
  findings, and emit review reports/packets. Findings are **clues for human review**;
  nothing is auto-written to the `people` conclusions.
- **Website** — `src/build_*.py` are static-site generators that read the database and
  emit self-contained HTML views (Browse, Family Tree, Fan chart, 3D connections,
  Timeline, World map, Storybook, Castles, Notable, Gallery, Ask-the-AI). Deployed to
  **Cloudflare Pages** with `wrangler`.
- **MCP server** — a Cloudflare Worker backed by D1 at
  `https://troytree-mcp.troyfernald.workers.dev`, powering the "Ask the AI" page.

Moving it to another PC means moving **three** things: the **code** (git), the
**local-only assets** (database, media, secrets — *not* in git), and the **credentials**
to deploy. Sections 1–6 are the migration checklist; section 7 documents the pipeline,
the website, and the research loop.

---

## 1. What you're moving

**A. Code — via git** (this repo, pushed to GitHub):
```
git clone https://github.com/TroyFernald/troyTree.git C:\tree\troy-family-tree-research
```

**B. Local-only assets — via the handoff bundle** (NOT in git; `.gitignore` excludes the
database, media, exports, and secrets):

| Asset | Location | Notes |
|---|---|---|
| Working database | `data/working/research.sqlite` (~26 MB) | **Source of truth** for the site. Contains living-relative data — keep private. |
| Curated + generated exports | `data/exports/` | deep-dives, findings, packets, research batches, geocode cache, built HTML, bundled `media/` |
| Original import DB | `data/original/` + `Troy Tree.ged` | the GEDCOM and pilot data |
| Secrets | `data/site_password.txt`, `data/access_allowlist.txt` | site gate password + allowlist |
| RootsMagic source | `C:\Tree\ancestory-import.rmtree` | genealogy master; sync target from Ancestry |
| Media library | `C:\Tree\ancestory-import_media\` (~955 MB) | ~1,956 photos/documents the site links to |
| Newspaper dropbox | `C:\Tree\news_dropbox\` | subscription clippings you drop for ingest |
| Deploy dir | `C:\troytree-dist\pub\` | the built site + bundled `media/`; what `wrangler` uploads |

Generate the bundle with:
```
powershell -ExecutionPolicy Bypass -File tools\make_handoff_bundle.ps1
```

**C. Cloud services — already live, nothing to migrate.** Just re-authenticate `wrangler`:
- Cloudflare **Pages** project `troytree` → **troytree.org** (the website, behind a shared family password)
- Cloudflare **D1** `troytree` (id `63b79f97-458a-49e5-8830-15e5c0813803`) — backs the MCP server
- Cloudflare **Worker** `troytree-mcp` → `https://troytree-mcp.troyfernald.workers.dev`
- GitHub backup repo for the published site: `https://github.com/TroyFernald/troy-family-site.git`

---

## 2. Prerequisites

- **Python 3.12**; install deps: `pip install -r requirements.txt`
- **Node.js 20+** (ships `npx`/`npm`); `npm install` in the repo gets `wrangler`
- **Tesseract OCR** at `C:\Program Files\Tesseract-OCR\tesseract.exe` (hard-coded in `src/ingest_news.py`)
- **Google Chrome** — used by the headless view tests (`tools/test_*.js`); `npm install puppeteer-core@23 --no-save`
- **git** and (optional) **gh**

---

## 3. Setup (in order)

1. Install prerequisites.
2. `git clone … C:\tree\troy-family-tree-research` (keep this exact path — see Gotchas).
3. `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
4. `npm install`
5. Restore local-only assets from the bundle's `RESTORE.ps1` (database, media, secrets,
   `C:\Tree\*`, and `C:\troytree-dist\pub`). This **overwrites** the stale `research.sqlite`
   shipped in git with the current one.
6. Authenticate: `npx wrangler login` (browser OAuth); `gh auth login` if using GitHub.
7. Verify (§4): rebuild a view, run pytest, run a headless test.

---

## 4. Build / deploy / test

**Rebuild the research database** from the GEDCOM (also normalizes sources):
```
python -m src.import_pilot_data
```

**Build the publishable site** into the deploy dir (photos served from the bundled `media/`):
```
python -c "from src.build_site import build_site; from pathlib import Path; print(build_site(media_base='media/', redact_living=True, out_dir=Path(r'C:\troytree-dist\pub'), archive_url=''))"
```

**Deploy to Cloudflare Pages production** (this is the real deploy — *not* the GitHub repo):
```
npx wrangler pages deploy C:/troytree-dist/pub --project-name=troytree --branch=main --commit-dirty=true
```

**Back up the published HTML to GitHub** (optional; deploy does not depend on it):
```
.\tools\publish.ps1      # builds into C:\tree\troy-family-site and pushes
```
> The site repo's `_worker.js` carries the family password and is **gitignored there** —
> never commit it.

**Tests:**
```
python -m pytest -q                 # 29 passing (unit tests)
node tools/test_tree.js             # headless: Family Tree (layout / zoom / hit-testing)
node tools/test_timeline_gap.js     # headless: Timeline research-gap color toggle
node tools/test_fly.js              # headless: 3D connections
node tools/test_timeline.js         # headless: Timeline zoom/hit-testing
```
Always headless-verify the interactive canvas views before claiming a fix — don't trust
code-by-inspection.

Other entry points: `python -m src.build_offline` (offline archive),
`python -m src.ingest_news ocr` (OCR the news dropbox), `python -m src.export_mcp_d1`
then `wrangler d1 ...` (refresh the MCP database).

---

## 5. Secrets & credentials

Not in git; they travel in the bundle.

| Secret | Where it lives |
|---|---|
| Site gate password | `data/site_password.txt` (baked into `_worker.js` at build; gitignored) |
| Access allowlist | `data/access_allowlist.txt` |
| MCP family token | Cloudflare Worker secret `FAMILY_TOKEN` (already set; re-set only when redeploying the worker) |
| Cloudflare access | `wrangler login` (per machine) |

> Never commit `research.sqlite`, `data/*.txt`, or the site repo's `_worker.js`. Never
> scrape Ancestry/Newspapers.com. Living people are redacted at build time
> (`redact_living=True`).

---

## 6. Gotchas

- **Hard-coded Windows paths.** `src/ingest_news.py` and `src/build_offline.py` reference
  `C:\Tree\ancestory-import_media`, `C:\troytree-dist`, and `C:\Tree\news_dropbox`. Keep the
  same layout (the bundle's `RESTORE.ps1` does this) or edit those constants.
- **`research.sqlite` in git is stale and contains living data** (force-added historically).
  The live DB in the bundle is newer. Consider scrubbing it from git history later.
- **Deploys go through `wrangler` from `C:\troytree-dist\pub`, not GitHub.** The
  `troy-family-site` GitHub repo is a backup of the published HTML only and can lag.
- **Photos** are served from the bundled `media/` folder inside the deploy dir (built with
  `media_base='media/'`). `wrangler` dedupes by hash, so re-deploys only upload changed files.
- **R2 not enabled** → no web download for the ~900 MB offline archive; it lives on the PC.
- **Cloudflare caches HTML briefly** — after a deploy, hard-refresh (Ctrl+F5) to see changes.
- LF→CRLF git warnings on Windows are harmless.

---

## 7. The pipeline, the website, and the research loop

### Research / evidence pipeline (`src/`)

- `init_database.py` — schema + migrations (`source` columns for normalized GEDCOM sources,
  duplicate/review columns).
- `gedcom_import.py` — parses `Troy Tree.ged`; imports people/families, raw records, per-record
  citation stubs, and evidence assertions. (It only *counts* `SOUR` lines.)
- **`gedcom_sources.py`** — deep source normalization: parses the real `0 @S..@ SOUR` +
  `0 @R..@ REPO` records (TITL/AUTH/PUBL/_APID/REPO) and every inline `SOUR @S..@` citation
  (PAGE/DATA/TEXT/WWW/QUAY) into normalized `repository`/`source`/`citation` rows, each
  attributed to the event it documents. Idempotent; runs after `gedcom_import` in the pipeline.
  Currently: **221 real sources, 2 repositories, 6,617 inline citations**.
- `import_pilot_data.py` — the full pipeline entry point (GEDCOM import → source normalization
  → pilot CSV import → duplicates → direct-ancestor audit → validation → web targets/findings →
  notable people → review tasks).
- `direct_ancestor_audit.py` — walks parents from the root, tags generations, and scores
  research **priority** (weak/no-source ancestors, gens 4–8, ME/NH/MA/NS, key surnames first).
- **`research_batch.py`** — prioritized public-web research batch runner. `plan [N]` writes
  agent-ready batch files (public-sources-only rules + finding schema, living excluded);
  `status` reports progress.
- `record_findings.py` — ingests agent findings (JSON) into `web_research_finding` +
  `evidence_candidates`; marks researched targets closed. Findings are clues, never written to
  `people`.
- **`evidence_packet.py`** — per-person Markdown review packet: profile, photos, transcribed
  documents, extracted evidence, **cited GEDCOM sources** (grouped, with page locators),
  military service, web findings, validation flags, and **possible duplicates**.

Current DB (approx): people 3,761 · family_relationships 10,872 · evidence_assertion 16,129 ·
web_research_target 27,721 · web_research_finding 708 · evidence_candidates ~1,036 ·
duplicate_candidates 391 · validation_issue 200 · notable_person_candidate 281.

### The public-web research loop (human-in-the-loop, public sources only)

```
python -m src.research_batch plan 60        # write prioritized batches to data/exports/research_batches/
# a research agent works each batch_NNN.json, searching PUBLIC sources only,
# and writes findings JSON into data/exports/findings/
python -m src.record_findings data/exports/findings   # ingest
python -m src.research_batch status          # what's left
```
Rules baked into every batch: public sources only; never use an Ancestry/Newspapers.com login
or scrape account-gated pages; every finding is a clue for review, not proof. (Gens 4–8 are
largely researched; the open frontier is gens 10–18.)

### Website views (`src/build_*.py` → `build_site.py`)

Generators emit HTML into `data/exports/`; `build_site.py` collects the publishable set into the
deploy dir + a landing page. Views: Browse (`family.html`), **Family Tree (`tree.html`)**,
Fan chart (`fan.html`), 3D connections (`graph_3d.html`), **Timeline (`timeline.html`)**, World
map (`map.html`), Storybook (`story.html`), Castles, Notable, Gallery, Research guide, Review,
Ask-the-AI (`connect.html`).

- **Family Tree (`build_tree.py`)** — a true direct-line pedigree: you at the bottom point;
  each child's two parents go **up and out to the sides** over their own ancestry, every family
  in its own column so the **connector lines never cross**; child sits at the midpoint of its
  parents (point-down triangle, all 19 generations, direct line only). Narrow vertical cards
  (photo on top, given name over surname, dates), notable ★ badges, click → story, silky canvas
  zoom. Headless-tested by `tools/test_tree.js`. **Do not** revert to the rejected layouts
  (sideways left-to-right; centered-rows whose lines cross; couples stretched wide). See
  `docs/` and the layout comment in `build_tree.py`.
- **Timeline (`build_timeline.py`)** — every relative's lifespan; a **"Color: By side /
  Research gaps"** toggle shades bars by sourcing (`_gap_level`). Headless-tested by
  `tools/test_timeline_gap.js`.

---

## 8. Repo map

```
src/            research pipeline (gedcom_import, gedcom_sources, import_pilot_data,
                direct_ancestor_audit, research_batch, record_findings, evidence_packet, …)
                + site generators (build_*.py incl. build_tree), ingest_news, export_mcp_d1, paths.py
cloudflare/     mcp-worker/ (worker.js, wrangler.toml, README)
config/         confidence_rules / sources / web_research_seeds (yaml)
data/           working/ (db) · exports/ (generated+curated: packets/, research_batches/,
                findings/, media/) · original/ · secrets   [gitignored]
tools/          make_handoff_bundle.ps1, publish.ps1, test_tree.js, test_timeline_gap.js,
                test_fly.js, test_timeline.js
tests/          pytest unit tests (29 passing)
docs/           session_handoff (research-pipeline detail), GO-LIVE, MIGRATION, best-practices
```
