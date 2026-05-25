/**
 * Troy Family Tree — hosted MCP server (Cloudflare Worker).
 *
 * Exposes the (redacted) family database to AI clients as read-only MCP tools
 * over Streamable HTTP. A relative points their own AI client at this Worker's
 * URL with the family token and can ask plain-English questions; the AI calls
 * these tools to answer from the real data.
 *
 * Safety: read-only (SELECT-only tools, no arbitrary SQL), token-gated, living
 * people already excluded from the D1 data by src/export_mcp_d1.py. Bind a D1
 * database as `DB` and set the secret `FAMILY_TOKEN` (see README.md).
 */

const PROTOCOL_VERSION = "2024-11-05";

const TOOLS = [
  { name: "find_person", description: "Find people by name (partial match). Returns id, dates, generation, side, and how they relate to the root person.",
    inputSchema: { type: "object", properties: { name: { type: "string", description: "Full or partial name" } }, required: ["name"] } },
  { name: "person_details", description: "Full detail for one person by person_id: dates, places, parents, spouse(s), children, and how they relate to the root.",
    inputSchema: { type: "object", properties: { person_id: { type: "string" } }, required: ["person_id"] } },
  { name: "list_ancestors", description: "List the direct ancestors of a person up to N generations back.",
    inputSchema: { type: "object", properties: { person_id: { type: "string" }, generations: { type: "integer", description: "How many generations back (default 6, max 20)" } }, required: ["person_id"] } },
  { name: "search_records", description: "Search research findings, newspaper clippings, and notable reasons for a keyword (e.g. a place, occupation, war, surname).",
    inputSchema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] } },
  { name: "notable_ancestors", description: "List notable ancestors, optionally filtered by category (mayflower, military_title, royal_noble, medieval_descent, colonial_public_figure).",
    inputSchema: { type: "object", properties: { category: { type: "string" } }, required: [] } },
];

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return cors(new Response(null, { status: 204 }));

    // --- auth: bearer header or ?key= ---
    const url = new URL(request.url);
    const token = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "") || url.searchParams.get("key") || "";
    if (!env.FAMILY_TOKEN || token !== env.FAMILY_TOKEN) {
      return cors(jsonResponse({ jsonrpc: "2.0", error: { code: -32001, message: "Unauthorized" } }, 401));
    }

    // Some clients open a GET SSE stream first; keep it harmlessly alive.
    if (request.method === "GET") {
      return cors(new Response("event: ready\ndata: {}\n\n", { headers: { "content-type": "text/event-stream", "cache-control": "no-cache" } }));
    }
    if (request.method !== "POST") return cors(jsonResponse({ error: "Method not allowed" }, 405));

    let body;
    try { body = await request.json(); } catch { return cors(jsonResponse({ error: "Bad JSON" }, 400)); }
    const batch = Array.isArray(body);
    const out = [];
    for (const msg of (batch ? body : [body])) {
      const r = await handle(msg, env);
      if (r) out.push(r);
    }
    if (!out.length) return cors(new Response(null, { status: 202 }));
    return cors(jsonResponse(batch ? out : out[0]));
  },
};

async function handle(msg, env) {
  const { id, method, params } = msg || {};
  if (method === "initialize")
    return rpc(id, { protocolVersion: PROTOCOL_VERSION, capabilities: { tools: {} }, serverInfo: { name: "Troy Family Tree", version: "1.0.0" } });
  if (method === "ping") return rpc(id, {});
  if (typeof method === "string" && method.startsWith("notifications/")) return null; // no response to notifications
  if (method === "tools/list") return rpc(id, { tools: TOOLS });
  if (method === "tools/call") {
    try {
      const text = await callTool(params?.name, params?.arguments || {}, env);
      return rpc(id, { content: [{ type: "text", text }], isError: false });
    } catch (e) {
      return rpc(id, { content: [{ type: "text", text: "Error: " + (e && e.message || e) }], isError: true });
    }
  }
  return rpc(id, undefined, { code: -32601, message: "Method not found: " + method });
}

async function callTool(name, args, env) {
  const db = env.DB;
  if (name === "find_person") {
    const rows = await db.prepare(
      "SELECT person_id, full_name, birth_date, death_date, generation, side, relationship_to_root " +
      "FROM people WHERE full_name LIKE ? ORDER BY (generation IS NULL), generation LIMIT 30"
    ).bind("%" + (args.name || "") + "%").all();
    return j(rows.results);
  }
  if (name === "person_details") {
    const p = await db.prepare("SELECT * FROM people WHERE person_id = ?").bind(args.person_id).first();
    if (!p) return "No person with that id (they may be a living person, who are not included).";
    const parents = await db.prepare("SELECT pe.full_name, pe.birth_date, pe.death_date FROM rel r JOIN people pe ON pe.person_id=r.parent_id WHERE r.child_id=? AND r.kind='parent'").bind(args.person_id).all();
    const children = await db.prepare("SELECT pe.full_name, pe.birth_date, pe.death_date FROM rel r JOIN people pe ON pe.person_id=r.child_id WHERE r.parent_id=? AND r.kind='parent'").bind(args.person_id).all();
    const spouses = await db.prepare("SELECT pe.full_name FROM rel r JOIN people pe ON pe.person_id=r.child_id WHERE r.parent_id=? AND r.kind='spouse' UNION SELECT pe.full_name FROM rel r JOIN people pe ON pe.person_id=r.parent_id WHERE r.child_id=? AND r.kind='spouse'").bind(args.person_id, args.person_id).all();
    const findings = await db.prepare("SELECT source_title, source_type, substr(claimed_facts,1,260) AS facts FROM finding WHERE person_id=? LIMIT 8").bind(args.person_id).all();
    return j({ person: p, parents: parents.results, spouses: spouses.results.map(s => s.full_name), children: children.results, findings: findings.results });
  }
  if (name === "list_ancestors") {
    const gens = Math.max(1, Math.min(20, parseInt(args.generations || 6, 10) || 6));
    const rows = await db.prepare(
      "WITH RECURSIVE anc(pid, depth) AS (" +
      "  SELECT parent_id, 1 FROM rel WHERE child_id=?1 AND kind='parent'" +
      "  UNION ALL SELECT r.parent_id, anc.depth+1 FROM rel r JOIN anc ON r.child_id=anc.pid WHERE r.kind='parent' AND anc.depth<?2 )" +
      " SELECT DISTINCT anc.depth, p.full_name, p.birth_date, p.death_date, p.birth_place, p.side " +
      " FROM anc JOIN people p ON p.person_id=anc.pid ORDER BY anc.depth, p.full_name LIMIT 400"
    ).bind(args.person_id, gens).all();
    return j(rows.results);
  }
  if (name === "search_records") {
    const q = "%" + (args.query || "") + "%";
    const rows = await db.prepare(
      "SELECT person_name, source_title, source_type, substr(coalesce(claimed_facts,snippet),1,300) AS text " +
      "FROM finding WHERE claimed_facts LIKE ?1 OR snippet LIKE ?1 OR person_name LIKE ?1 " +
      "UNION ALL SELECT person_name, 'notable' AS source_title, category AS source_type, notable_reason AS text " +
      "FROM notable WHERE notable_reason LIKE ?1 OR person_name LIKE ?1 LIMIT 40"
    ).bind(q).all();
    return j(rows.results);
  }
  if (name === "notable_ancestors") {
    let rows;
    if (args.category)
      rows = await db.prepare("SELECT person_name, category, notable_reason FROM notable WHERE category=? LIMIT 100").bind(args.category).all();
    else
      rows = await db.prepare("SELECT person_name, category, notable_reason FROM notable LIMIT 200").all();
    return j(rows.results);
  }
  throw new Error("Unknown tool: " + name);
}

const j = (v) => JSON.stringify(v);
const rpc = (id, result, error) => error ? { jsonrpc: "2.0", id, error } : { jsonrpc: "2.0", id, result };
function jsonResponse(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });
}
function cors(resp) {
  const h = new Headers(resp.headers);
  h.set("Access-Control-Allow-Origin", "*");
  h.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  h.set("Access-Control-Allow-Headers", "authorization, content-type, mcp-protocol-version, mcp-session-id");
  return new Response(resp.body, { status: resp.status, headers: h });
}
