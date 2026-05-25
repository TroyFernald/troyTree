"""Build ``connect.html`` — instructions for attaching your own AI to the tree.

Explains, for family members, how to connect an AI client (Claude Desktop, etc.)
to the hosted MCP server so they can ask the database questions in plain English.
Static page; the owner pastes the live Worker URL + token once it's deployed.

    python -m src.build_mcp_page
"""

from __future__ import annotations

from .paths import EXPORTS_DIR, WORKING_DB

OUT_PATH = EXPORTS_DIR / "connect.html"


def build(db_path=WORKING_DB) -> dict:
    OUT_PATH.write_text(_PAGE, encoding="utf-8")
    return {"out": str(OUT_PATH)}


_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Troy Family Tree · Ask the AI</title>
<style>
  :root{--bg:#f4efe7;--ink:#3a2f25;--accent:#7a5c3e;--line:#e3dac9;--card:#fff;}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 Georgia,"Times New Roman",serif;}
  header{padding:16px 20px 6px;font-family:-apple-system,Segoe UI,Roboto,sans-serif;}
  header a.home{color:var(--accent);text-decoration:none;font-size:14px;}
  .doc{max-width:760px;margin:0 auto;padding:8px 22px 80px;}
  h1{font-size:30px;margin:.3em 0 .1em;}
  h2{font-size:21px;margin:1.5em 0 .3em;color:var(--accent);border-bottom:1px solid var(--line);padding-bottom:4px;}
  p,li{font-size:16px;}
  code,pre{font-family:ui-monospace,Consolas,monospace;}
  code{background:#ece3d4;padding:1px 5px;border-radius:4px;font-size:.92em;}
  pre{background:#1f1a12;color:#f0e8d6;padding:14px 16px;border-radius:9px;overflow:auto;font-size:13px;line-height:1.5;}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:14px 0;}
  .ask{font-style:italic;color:#5b4a35;}
  .note{background:#fbf3e7;border-left:4px solid var(--accent);padding:10px 14px;border-radius:6px;font-size:14.5px;font-family:-apple-system,Segoe UI,sans-serif;}
  .ph{color:#a85;font-weight:bold;}
  ul{padding-left:20px;}
</style>
</head>
<body>
<header><a class="home" href="index.html">‹ Home</a></header>
<article class="doc">
<h1>🤖 Ask the AI about our family</h1>
<p>You can connect <b>your own AI assistant</b> to the family tree and ask it questions in
plain English — it reads the real database and answers. Nothing about living family
members is shared; the AI only sees the same redacted history that's on this site, and it
can only read (never change) the data.</p>

<div class="card">
<b>Try asking things like:</b>
<ul>
  <li class="ask">"How am I related to John Howland of the Mayflower?"</li>
  <li class="ask">"List my ancestors who were born in Troy, Maine."</li>
  <li class="ask">"What newspaper stories mention Clyde Fernald?"</li>
  <li class="ask">"Show me the notable military ancestors."</li>
  <li class="ask">"Trace Medwin Fernald's ancestors back six generations."</li>
</ul>
</div>

<h2>What you need from the family</h2>
<p>Two things (ask whoever runs the site):</p>
<ul>
  <li>The <b>server address</b> — looks like <code class="ph">https://troytree-mcp.&lt;name&gt;.workers.dev</code></li>
  <li>The <b>family token</b> — a secret password for the AI connection</li>
</ul>

<h2>Connect with Claude Desktop (easiest)</h2>
<ol>
  <li>Install the free <b>Claude Desktop</b> app.</li>
  <li>Open <b>Settings → Developer → Edit Config</b> (this opens <code>claude_desktop_config.json</code>).</li>
  <li>Add the block below, pasting in the server address and token, then save and restart Claude:</li>
</ol>
<pre>{
  "mcpServers": {
    "troy-family-tree": {
      "command": "npx",
      "args": ["mcp-remote", "<span class="ph">https://YOUR-SERVER-URL</span>/?key=<span class="ph">FAMILY-TOKEN</span>"]
    }
  }
}</pre>
<p>Now just chat with Claude: ask any of the questions above and it will look up the
answers from the family tree. You'll see it call tools like <code>find_person</code> or
<code>list_ancestors</code> as it works.</p>

<div class="note">
Other MCP-capable AI clients work too — point them at the same server address with the
token. The connection is read-only and protected by the token, so only people you share
it with can use it.
</div>

<h2>For whoever runs the site</h2>
<p>The server is a small Cloudflare Worker in <code>cloudflare/mcp-worker/</code> of the
project. Its <code>README.md</code> has the one-time deploy steps (create a D1 database,
import the redacted data with <code>python -m src.export_mcp_d1</code>, set the
<code>FAMILY_TOKEN</code> secret, and <code>wrangler deploy</code>). Re-run the export and
deploy whenever the research is updated.</p>
</article>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
