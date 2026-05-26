# Troy Family Tree — Handoff to a new PC

This project builds a private, password-protected family-heritage website from a
research database and deploys it to Cloudflare Pages. Static-site generators in
`src/` read `data/working/research.sqlite` and emit self-contained HTML (Browse,
3D connections, Fan chart, Timeline, World map, Storybook, Castles, Notable,
Gallery, Ask-the-AI). It's deployed with `wrangler`; a read-only MCP server (a
Cloudflare Worker backed by D1) powers the "Ask the AI" page.

Moving it to another PC means moving **three** things: the **code** (git), the
**local-only assets** (database, media, secrets — *not* in git), and the
**credentials** to deploy. This file is the checklist.

---

## 1. What you're moving

**A. Code — via git** (already pushed):
```
git clone https://github.com/TroyFernald/troyTree.git C:\tree\troy-family-tree-research
```

**B. Local-only assets — via the handoff bundle** (NOT in git; `.gitignore` excludes the database, media, exports, and secrets):

| Asset | Current location | Size | Notes |
|---|---|---|---|
| Working database | `data/working/research.sqlite` | 25 MB | **Source of truth** for the site. Contains living-relative data — keep private. |
| Curated + generated exports | `data/exports/` | 88 MB | deep-dives, `dd_batch*`, findings, geocode cache, built HTML |
| Original import DB | `data/original/` | 3.5 MB | |
| Secrets | `data/site_password.txt`, `data/access_allowlist.txt` | tiny | site gate password + allowlist |
| RootsMagic source | `C:\Tree\ancestory-import.rmtree` | 10 MB | the genealogy master; sync target from Ancestry |
| Media library | `C:\Tree\ancestory-import_media\` | **955 MB** | ~1,956 photos/documents the site links to |
| Newspaper dropbox | `C:\Tree\news_dropbox\` | 36 MB | subscription clippings you drop for ingest |

Generate the bundle with:
```
powershell -ExecutionPolicy Bypass -File tools\make_handoff_bundle.ps1
```
It writes `C:\troytree-handoff\` (~1.1 GB) with a `RESTORE.ps1` and `MANIFEST.txt`.
`C:\troytree-dist\` (2.8 GB — the built site + offline archive) is **regenerable**
and skipped by default (`-IncludeDist` to include it).

**C. Cloud services — already live, nothing to migrate.** Just re-authenticate
`wrangler` on the new PC:
- Cloudflare **Pages** project `troytree` (the website)
- Cloudflare **D1** database `troytree` (id `63b79f97-458a-49e5-8830-15e5c0813803`) — backs the MCP server
- Cloudflare **Worker** `troytree-mcp` at `https://troytree-mcp.troyfernald.workers.dev`
- DNS via Cloudflare; GitHub repo backup. (R2 is **not** enabled — the offline-archive web download link is still blocked on enabling R2 in the dashboard.)

---

## 2. Prerequisites to install on the new PC

- **Python 3.12** (matches current)
- **Node.js 20+** (current: v24; ships `npx`/`npm`)
- **Tesseract OCR** at `C:\Program Files\Tesseract-OCR\tesseract.exe` (hard-coded in `src/ingest_news.py`) — install from the UB-Mannheim build
- **Google Chrome** (used by the headless view tests in `tools/test_*.js`)
- **git** and (optional) **gh** CLI
- `wrangler` comes via `npm install` in the repo

---

## 3. Setup steps (in order)

1. Install the prerequisites above.
2. `git clone … C:\tree\troy-family-tree-research` (keep this exact path — see Gotchas).
3. Python deps:
   ```
   cd C:\tree\troy-family-tree-research
   python -m venv .venv && .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Node deps: `npm install` (gets wrangler). For the view tests only: `npm install puppeteer-core@23 --no-save`.
5. Restore the local-only assets: copy the handoff bundle to the new PC and run `RESTORE.ps1` (puts the database, media, secrets, and `C:\Tree\*` back in place). This **overwrites** the stale `research.sqlite` that ships in the git repo with the current one.
6. Authenticate: `npx wrangler login` (browser OAuth) and, if using GitHub, `gh auth login`.
7. Verify (see §4): a build, then a headless test.

---

## 4. Build / deploy / test

Rebuild the publishable site into the deploy dir (media served relatively):
```
python -c "from src.build_site import build_site; build_site(media_base='media/', redact_living=True, out_dir=__import__('pathlib').Path(r'C:\troytree-dist\pub'), archive_url='')"
```
Deploy to Cloudflare Pages production:
```
npx wrangler pages deploy C:/troytree-dist/pub --project-name=troytree --branch=main --commit-dirty=true
```
Headless-verify the interactive canvas views before claiming a fix:
```
node tools/test_fly.js          # 3D connections (fly / labels)
node tools/test_timeline.js     # Timeline (zoom / hit-testing)
```
Other useful entry points: `python -m src.build_offline` (offline archive),
`python -m src.ingest_news ocr` (OCR the news dropbox), `python -m src.export_mcp_d1`
then `wrangler d1 ...` (refresh the MCP database).

---

## 5. Secrets & credentials

Values are **not** in git; they travel in the bundle (and are recorded in the
operator's notes). Restore destinations:

| Secret | Where it lives | Value |
|---|---|---|
| Site gate password | `data/site_password.txt` (baked into `_worker.js` at build) | in the bundle |
| Access allowlist | `data/access_allowlist.txt` | in the bundle |
| MCP family token | Cloudflare Worker secret `FAMILY_TOKEN` (already set in the cloud) | re-set only if redeploying the worker: `printf '<token>' \| npx wrangler secret put FAMILY_TOKEN` |
| Cloudflare access | `wrangler login` (browser) | per-machine |

> Never commit `research.sqlite`, `data/*.txt`, or `access_allowlist.txt`. Never
> scrape Ancestry/Newspapers.com. Living people are redacted at build time.

---

## 6. Gotchas

- **Hard-coded Windows paths.** `src/ingest_news.py` and `src/build_offline.py`
  reference `C:\Tree\ancestory-import_media`, `C:\troytree-dist`, and
  `C:\Tree\news_dropbox`. Keep the same layout on the new PC (the bundle's
  `RESTORE.ps1` does this) or edit those constants.
- **`research.sqlite` in git is stale and contains living data.** It was
  force-added historically. The live DB in the bundle is newer (has the latest
  newspaper clippings/deep-dives) — `RESTORE.ps1` overwrites the repo copy with it.
  Consider scrubbing it from git history later if the repo's privacy matters.
- **R2 not enabled** → no web download for the 900 MB offline archive; it lives
  on the PC only until R2 is turned on in the Cloudflare dashboard.
- **LF→CRLF git warnings** on commit are harmless on Windows.
- Deploys go through `wrangler`, **not** GitHub — pushing to GitHub is backup only.

---

## 7. Repo map

```
src/            build_*.py site generators, ingest_news, export_mcp_d1, paths.py
cloudflare/     mcp-worker/ (worker.js, wrangler.toml, README)
config/         confidence_rules / sources / web_research_seeds (yaml)
data/           working/ (db) · exports/ (generated+curated) · original/ · secrets  [gitignored]
tools/          make_handoff_bundle.ps1, test_fly.js, test_timeline.js
docs/           GO-LIVE, MIGRATION, session_handoff, best-practices
```
