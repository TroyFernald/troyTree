# Moving this project to a new PC

The project is three parts that move differently. Keep the same root path
(`C:\Tree`) on the new machine and everything lines up.

## 1. Code — via Git (small, version-controlled)
On the new PC:
```
git clone https://github.com/TroyFernald/troyTree.git C:\Tree\troy-family-tree-research
git clone https://github.com/TroyFernald/troy-family-site.git C:\Tree\troy-family-site
```
That brings all the generators (`src/`), tests, `config/`, and docs.

## 2. Data + media — by file copy (NOT in Git: private + too large)
These are intentionally kept out of Git. Copy them from the old PC's `C:\Tree`
to the new PC's `C:\Tree` (USB drive, network share, or the Google Drive backup):
- `troy-family-tree-research\data\working\research.sqlite`  ← the working database (the heart of it)
- `troy-family-tree-research\data\original\`  ← GEDCOM + source CSVs
- `troy-family-tree-research\data\access_allowlist.txt`  ← family access emails (keep private)
- `ancestory-import_media\`  ← 914 MB of photos & documents
- `ancestory-import.rmtree`  ← RootsMagic file

**Easiest:** just copy the whole `C:\Tree` folder — it contains all of the above
plus both repos (their `.git` included).

## 3. Tools to install on the new PC
- **Python 3.12+** → then `pip install -r requirements.txt`
- **Node.js** (for Wrangler / Cloudflare deploys)
- **Tesseract OCR** at `C:\Program Files\Tesseract-OCR\` (only if re-running OCR)
- **GitHub CLI:** `gh auth login`  (re-auth as TroyFernald)
- **Cloudflare:** `npx wrangler login`  (credentials don't copy; re-login)
- *(optional)* **Google Drive for Desktop** to re-establish the backup mirror

## 4. Verify
```
python -m pytest -q            # tests should pass
python -m src.build_site       # regenerates the site bundle from the DB
```
Publishing/updating is unchanged: `tools\publish.ps1` (after `wrangler login`),
or `npx wrangler pages deploy` for the media-bundled deploy.

## 5. Assistant memory (optional)
To carry the assistant's project memory over, also copy
`C:\Users\<you>\.claude\projects\C--tree\memory\` to the same path on the new PC
(this works as long as the project stays at `C:\Tree`).
