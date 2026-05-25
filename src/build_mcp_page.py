"""Build ``connect.html`` — instructions for attaching your own AI to the tree.

Explains why it's useful and exactly how a family member connects an AI client
(Claude Desktop, etc.) to the hosted MCP server, with the live server address and
family token filled in. Update MCP_URL / MCP_TOKEN if the Worker is redeployed.

    python -m src.build_mcp_page
"""

from __future__ import annotations

from .paths import EXPORTS_DIR, WORKING_DB

OUT_PATH = EXPORTS_DIR / "connect.html"

MCP_URL = "https://troytree-mcp.troyfernald.workers.dev"
MCP_TOKEN = "fernald-family-2026"


def build(db_path=WORKING_DB) -> dict:
    page = (_PAGE.replace("__URL__", MCP_URL).replace("__TOKEN__", MCP_TOKEN)
                 .replace("__CONNECT__", f"{MCP_URL}/?key={MCP_TOKEN}"))
    OUT_PATH.write_text(page, encoding="utf-8")
    return {"out": str(OUT_PATH), "url": MCP_URL}


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
  code{background:#ece3d4;padding:1px 5px;border-radius:4px;font-size:.92em;font-family:ui-monospace,Consolas,monospace;}
  pre{background:#1f1a12;color:#f0e8d6;padding:14px 16px;border-radius:9px;overflow:auto;font-size:13px;line-height:1.5;font-family:ui-monospace,Consolas,monospace;}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:14px 0;}
  .ask{font-style:italic;color:#5b4a35;}
  .creds{font-family:-apple-system,Segoe UI,sans-serif;}
  .creds .row{margin:6px 0;}
  .creds .k{color:#8a7866;font-size:13px;display:block;}
  .creds .v{font-family:ui-monospace,Consolas,monospace;font-size:15px;background:#f3ecdd;padding:4px 8px;border-radius:6px;display:inline-block;word-break:break-all;}
  .note{background:#fbf3e7;border-left:4px solid var(--accent);padding:10px 14px;border-radius:6px;font-size:14.5px;font-family:-apple-system,Segoe UI,sans-serif;}
  ul{padding-left:20px;}
</style>
</head>
<body>
<header><a class="home" href="index.html">‹ Home</a></header>
<article class="doc">
<h1>🤖 Ask the AI about our family</h1>
<p>You can connect <b>your own AI assistant</b> to the family tree and just ask it questions
in plain English — it reads the real database (over 3,700 relatives) and answers.</p>

<h2>Why this is useful</h2>
<ul>
  <li><b>No genealogy software to learn.</b> Instead of clicking through charts, you ask
      a question and get an answer.</li>
  <li><b>It knows the whole tree.</b> Relationships, dates, places, birth/marriage/death
      records, newspaper clippings, and notable ancestors — all queryable at once.</li>
  <li><b>It does the tracing for you.</b> "How am I related to this person?" or "walk my
      ancestors back six generations" takes one sentence instead of an afternoon.</li>
  <li><b>Everyone uses their own AI.</b> Each relative connects from their own computer;
      it always reflects the latest research.</li>
  <li><b>Private &amp; safe.</b> It's read-only, password-protected, and living family
      members are never included.</li>
</ul>

<div class="card">
<b>Try asking your AI:</b>
<ul>
  <li class="ask">"How am I related to John Howland of the Mayflower?"</li>
  <li class="ask">"List my ancestors who were born in Troy, Maine."</li>
  <li class="ask">"What newspaper stories mention Clyde Fernald?"</li>
  <li class="ask">"Show me the notable military ancestors."</li>
  <li class="ask">"Trace Medwin Fernald's ancestors back six generations."</li>
</ul>
</div>

<h2>Connection details</h2>
<div class="card creds">
  <div class="row"><span class="k">Server address</span><span class="v">__URL__</span></div>
  <div class="row"><span class="k">Family token (keep it in the family)</span><span class="v">__TOKEN__</span></div>
</div>

<h2>Connect with Claude Desktop (easiest)</h2>
<ol>
  <li>Install the free <b>Claude Desktop</b> app and sign in.</li>
  <li>Open <b>Settings → Developer → Edit Config</b> (this opens <code>claude_desktop_config.json</code>).</li>
  <li>Paste in the block below exactly, then save and restart Claude:</li>
</ol>
<pre>{
  "mcpServers": {
    "troy-family-tree": {
      "command": "npx",
      "args": ["mcp-remote", "__CONNECT__"]
    }
  }
}</pre>
<p>Now just chat: ask any of the questions above and Claude will look the answers up from
the family tree (you'll see it call tools like <code>find_person</code> and
<code>list_ancestors</code> as it works).</p>

<div class="note">
Any MCP-capable AI client works — point it at the server address above with the token.
The connection is read-only and protected by the token, so only people you share it with
can use it. If the token ever leaks, whoever runs the site can change it in a minute.
</div>
</article>
</body>
</html>
"""


if __name__ == "__main__":
    print(build())
