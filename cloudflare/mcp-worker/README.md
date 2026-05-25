# Troy Family Tree — hosted MCP server

A Cloudflare Worker that lets family members attach **their own AI** (Claude
Desktop, etc.) and ask questions against the family database — e.g. *"How am I
related to John Howland?"* or *"List everyone born in Troy before 1850."*

It is **read-only**, **token-gated**, and serves only the **redacted** data
(living people are excluded by `src/export_mcp_d1.py`, same as the website).

## One-time deploy (you run this — needs your Cloudflare account)

From this folder (`cloudflare/mcp-worker/`):

```bash
npm install -g wrangler        # if you don't have it
wrangler login

# 1. Create the D1 database, then paste the printed database_id into wrangler.toml
wrangler d1 create troytree

# 2. Build the redacted seed file and import it
#    (run the export from the project root first)
cd ../..
python -m src.export_mcp_d1
cd cloudflare/mcp-worker
wrangler d1 execute troytree --remote --file=../../data/exports/mcp_seed.sql

# 3. Set the family access token (any strong string; share it with family)
wrangler secret put FAMILY_TOKEN

# 4. Deploy
wrangler deploy
```

`wrangler deploy` prints your server URL, e.g.
`https://troytree-mcp.<your-subdomain>.workers.dev`.
(Optionally add a custom route like `mcp.troytree.org` in the Cloudflare
dashboard → Workers → Triggers.)

## Refreshing the data later

After new research, re-run steps 2 + 4:

```bash
python -m src.export_mcp_d1
wrangler d1 execute troytree --remote --file=../../data/exports/mcp_seed.sql
wrangler deploy
```

## How relatives connect their AI

Give them the **server URL** and the **FAMILY_TOKEN**. The simplest client is
Claude Desktop via `mcp-remote` — add this to their MCP config
(`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "troy-family-tree": {
      "command": "npx",
      "args": ["mcp-remote", "https://YOUR-WORKER-URL/?key=FAMILY_TOKEN"]
    }
  }
}
```

Then they can just ask their AI questions in plain English. The site's
**"Ask the AI"** page shows these same instructions for the family.

## Tools the AI can call
- `find_person(name)` — look someone up
- `person_details(person_id)` — dates, parents, spouse, children, findings
- `list_ancestors(person_id, generations)` — direct line back
- `search_records(query)` — findings / newspaper clippings / notable reasons
- `notable_ancestors(category?)` — Mayflower, military, royal/noble, etc.

No arbitrary SQL is exposed; every tool is a fixed, read-only query.
