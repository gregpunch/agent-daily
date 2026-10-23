// Agent Daily MCP server: stateless, read-only, Streamable HTTP (JSON responses).
const STATUS_URL = "https://gregpunch.github.io/agent-daily/status.json";
const PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];
const INFO = { name: "agent-daily", title: "Agent Daily", version: "0.1.0" };
const RO = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true };
const TOOLS = [
  { name: "list_tools", title: "List monitored tools",
    description: "List the APIs and MCP servers Agent Daily monitors, with current up/down, latency and vendor status. Call before choosing a provider. Optional category filter (e.g. LLM, MCP, Search, Payments, Comms, Infra).",
    inputSchema: { type: "object", properties: { category: { type: "string", description: "Case-insensitive category filter" } } }, annotations: RO },
  { name: "tool_status", title: "Get one tool's status",
    description: "Full status record for one monitored tool (up, http_status, latency_ms, vendor_status, uptime_24h_pct). Case-insensitive name or substring, e.g. 'openai', 'GitHub MCP'. Reachability only, not correctness.",
    inputSchema: { type: "object", properties: { name: { type: "string" } }, required: ["name"] }, annotations: RO },
];
const CARD = { serverInfo: INFO, authentication: { required: false }, tools: TOOLS, resources: [], prompts: [] };
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type, mcp-protocol-version, mcp-session-id, accept", "Access-Control-Allow-Methods": "POST, GET, OPTIONS" };
const json = (b, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { "content-type": "application/json", ...CORS } });

let mem = null; // per-isolate cache
async function status() {
  if (mem && Date.now() - mem.t < 300e3) return mem.d;
  const r = await fetch(STATUS_URL, { cf: { cacheTtl: 300, cacheEverything: true } });
  if (!r.ok) throw new Error(`status.json HTTP ${r.status}`);
  const d = await r.json(); mem = { t: Date.now(), d }; return d;
}
const stale = (d) => Date.now() - Date.parse(d.generated_at) > 2 * 3600e3;
const text = (o) => ({ content: [{ type: "text", text: JSON.stringify(o, null, 1) }], structuredContent: o });

async function callTool(name, a = {}) {
  const d = await status();
  const meta = { generated_at: d.generated_at, stale: stale(d), methodology: d.methodology };
  if (name === "list_tools") {
    const c = a.category?.toLowerCase();
    const tools = d.tools.filter(t => !c || t.category.toLowerCase() === c)
      .map(({ name, category, up, latency_ms, vendor_status }) => ({ name, category, up, latency_ms, vendor_status }));
    return text({ ...meta, count: tools.length, tools });
  }
  if (name === "tool_status") {
    if (!a.name) return { isError: true, content: [{ type: "text", text: "name is required" }] };
    const q = a.name.toLowerCase();
    const t = d.tools.find(t => t.name.toLowerCase() === q) || d.tools.find(t => t.name.toLowerCase().includes(q));
    if (!t) return { isError: true, content: [{ type: "text", text: `Unknown tool '${a.name}'. Known: ${d.tools.map(t => t.name).join(", ")}` }] };
    return text({ ...meta, tool: t });
  }
  return null;
}

async function rpc(m) {
  const { id, method, params = {} } = m;
  const ok = (result) => ({ jsonrpc: "2.0", id, result });
  const err = (code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
  if (m.jsonrpc !== "2.0" || typeof method !== "string") return err(-32600, "Invalid Request");
  if (id === undefined) return null; // notification (incl. notifications/initialized): no-op
  switch (method) {
    case "initialize": {
      const v = PROTOCOLS.includes(params.protocolVersion) ? params.protocolVersion : PROTOCOLS[0];
      return ok({ protocolVersion: v, capabilities: { tools: { listChanged: false } }, serverInfo: INFO,
        instructions: "Check tool_status before calling an external API; route around tools that are down or whose vendor_status is major/critical." });
    }
    case "ping": return ok({});
    case "tools/list": return ok({ tools: TOOLS });
    case "tools/call": {
      try { const r = await callTool(params.name, params.arguments); return r ? ok(r) : err(-32602, `Unknown tool: ${params.name}`); }
      catch (e) { return ok({ isError: true, content: [{ type: "text", text: `Upstream error: ${e.message}` }] }); }
    }
    default: return err(-32601, `Method not found: ${method}`);
  }
}

export default {
  async scheduled(event, env, ctx) {
    const r = await fetch("https://api.github.com/repos/gregpunch/agent-daily/actions/workflows/check.yml/dispatches", {
      method: "POST", headers: { authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`, accept: "application/vnd.github+json", "user-agent": "agent-daily-cron", "content-type": "application/json" },
      body: JSON.stringify({ ref: "main" }) });
    if (r.status !== 204) throw new Error(`dispatch failed HTTP ${r.status}: ${await r.text()}`);
  },
  async fetch(req) {
    const u = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (u.pathname === "/.well-known/mcp/server-card.json") return json(CARD);
    if (u.pathname === "/" ) return json({ ...INFO, mcp: u.origin + "/mcp", data: STATUS_URL });
    if (u.pathname !== "/mcp") return json({ error: "not found" }, 404);
    if (req.method === "GET") return new Response("SSE stream not supported; POST JSON-RPC to /mcp", { status: 405, headers: { Allow: "POST", ...CORS } });
    if (req.method === "DELETE") return new Response(null, { status: 405, headers: CORS });
    if (req.method !== "POST") return new Response(null, { status: 405, headers: CORS });
    let body; try { body = await req.json(); } catch { return json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }, 400); }
    const batch = Array.isArray(body);
    const out = (await Promise.all((batch ? body : [body]).map(rpc))).filter(Boolean);
    if (!out.length) return new Response(null, { status: 202, headers: CORS });
    return json(batch ? out : out[0]);
  },
};
