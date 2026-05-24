# Troy Family Tree — Go-Live Rollout

Sequenced so each phase unlocks the next. **[AGENT]** = done/handled by Claude in the
GitHub repo. **[YOU]** = a Cloudflare-account action only Troy can do (I have no
Cloudflare access by design).

Repo: `github.com/TroyFernald/troy-family-site` (private) · Domain: `troytree.org`

---

## Phase 0 — Build (DONE) [AGENT]
- [x] Five views + landing, generated from the research DB
- [x] Sides (Fernald/Bagley/Both), living-person redaction, mobile-friendly, Home links
- [x] World map (1,190 places), 21 passing tests
- [x] Repo is static + Pages-ready (no `vercel.json`); `tools/publish.ps1` rebuilds & pushes
- [x] Offline-archive generator (`src/build_offline.py`) ready

## Phase 1 — Get it LIVE [YOU] (~2 min)
Cloudflare → **Workers & Pages → Create → Pages → Connect to Git**
- Authorize the Cloudflare GitHub app → allow repo **`troy-family-site`**
- Build preset **None**, build command **empty**, output dir **`/`** → **Save and Deploy**
- ✅ Result: site live at `troy-family-site.pages.dev` (no photos/password yet)
- → send Claude the `*.pages.dev` URL for a live sanity check

## Phase 2 — Domain + password [YOU] (~5 min)
- Pages project → **Custom domains** → add **`troytree.org`** (auto DNS + SSL, same account)
- **Zero Trust → Access → Applications** → self-hosted app for `troytree.org`
  - Policy **Allow** → Emails from `data/access_allowlist.txt`
  - Login method **One-Time PIN**
- ✅ Result: `troytree.org`, gated to family by email code

## Phase 3 — Photos [YOU provision → AGENT wires]
- [YOU] Create **R2 bucket**; enable public access (or a `media.troytree.org` custom domain)
- [YOU] Upload the photos from `C:\Tree\ancestory-import_media` (dashboard, or rclone/wrangler — ask Claude for the command)
- [YOU] Send Claude the **public base URL** (e.g. `https://media.troytree.org/`)
- [AGENT] `python -m src.build_site <r2-url>` + push → photos live everywhere
- [AGENT] `python -m src.build_offline` → zip; [YOU] upload zip to R2; [AGENT] wires the Download button

## Phase 4 — Family photo contributions [YOU provision → AGENT builds]
- [YOU] Create **D1 database**; bind to Pages as `DB`; bind R2 as `MEDIA`
- [AGENT] Add `/functions/api/*` (upload + list) + `schema.sql` + Browse-view UI; push
- Verify live (instant publish, photos only). Then iterate.

---

### What unblocks the most right now
1. **Phase 1** (connect Pages) → the site is live.
2. **R2 bucket + public URL** → photos, offline archive, and contributions all open up.
