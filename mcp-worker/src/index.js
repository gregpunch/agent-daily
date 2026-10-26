// Agent Daily MCP server: stateless, read-only, Streamable HTTP (JSON responses).
const STATUS_URL = "https://gregpunch.github.io/agent-daily/status.json";
const PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];
const INFO = { name: "agent-daily", title: "Agent Daily", version: "0.2.0" };
const RO = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true };
const TOOLS = [
  { name: "recommend", title: "Recommend a healthy provider for a task",
    description: "Before calling an external API, ask which provider to use. Give a task phrase or category (e.g. 'send email', 'web search', 'llm', 'scrape a page', 'vector db', 'speech to text', 'payments', 'geocode'). Returns the top healthy pick plus 1-2 fallbacks ranked by live status, vendor status, 7-day uptime and latency, with a reason and data freshness.",
    inputSchema: { type: "object", properties: { task: { type: "string", description: "Task phrase or category" } }, required: ["task"] }, annotations: RO },
  { name: "incidents", title: "Recent incidents",
    description: "Outages (consecutive failed probes) and vendor status-page incidents with UTC start/end over the last N days (max 7). Optional provider name filter. Use to judge whether a failing API is a known incident.",
    inputSchema: { type: "object", properties: { name: { type: "string" }, days: { type: "number", default: 7 } } }, annotations: RO },
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
const HISTORY_URL = "https://gregpunch.github.io/agent-daily/history.json";
let hmem = null;
async function history() {
  if (hmem && Date.now() - hmem.t < 300e3) return hmem.d;
  const r = await fetch(HISTORY_URL, { cf: { cacheTtl: 300, cacheEverything: true } });
  if (!r.ok) throw new Error(`history.json HTTP ${r.status}`);
  const d = await r.json(); hmem = { t: Date.now(), d }; return d;
}
const SYN = [
  [/e-?mail|smtp|newsletter|inbox/, "email"], [/scrap|crawl|extract|read (a )?(web)?page|fetch (a )?(url|page)|html|markdown/, "scraping"],
  [/search|google|serp|look ?up|find (info|on the web)|news/, "search"], [/vector|embedding store|similarity|semantic index|rag/, "vector-db"],
  [/speech|voice|tts|text.to.speech|transcri|stt|audio/, "voice"], [/llm|chat|completion|language model|generate text|gpt|summari|reason/, "llm"],
  [/pay|charge|checkout|invoice|billing|subscription/, "payments"], [/sms|text message|phone/, "sms"],
  [/slack|discord|telegram|message|notify|chat app/, "messaging"], [/map|geocod|address|route|direction|location/, "maps"],
  [/weather|forecast|temperature/, "weather"], [/crm|contact|lead|deal|hubspot/, "crm"], [/database|postgres|sql|redis|table|storage|db\b|airtable/, "storage/db"],
  [/sandbox|execute code|run code|code.exec|python/, "code-exec"], [/browser|headless|automate a site/, "browser"],
  [/docs|documentation|library reference/, "docs"], [/zap|workflow|automation|integrat/, "automation"], [/github|repo|pull request|code/, "code"],
  [/notion|jira|task|ticket|project|asana|linear/, "productivity"], [/deploy|host|cdn|dns|infra/, "infra"], [/wiki|encyclop|fact/, "knowledge"],
  [/model hub|hugging ?face|ml model/, "ml-models"], [/error|monitor|sentry/, "monitoring"],
];
function resolveTask(q, cats) {
  const s = q.toLowerCase().trim();
  if (cats.includes(s)) return s;
  for (const [re, c] of SYN) if (re.test(s) && cats.includes(c)) return c;
  return cats.find(c => s.includes(c)) || null;
}
const VPEN = { minor: 15, major: 60, critical: 80, unavailable: 2 };
function score(t) {
  return (t.up ? 100 : 0) - (VPEN[t.vendor_status] || 0) - (t.open_incident ? 20 : 0) + ((t.uptime_7d_pct ?? 95) - 95) * 2
    - Math.min(30, (t.p50_ms ?? t.latency_ms ?? 1000) / 100);
}
function why(t) {
  return `${t.up ? "up" : "DOWN"} (HTTP ${t.http_status}), vendor ${t.vendor_status ?? "n/a"}, 7d uptime ${t.uptime_7d_pct ?? "?"}%, p50 ${t.p50_ms ?? t.latency_ms ?? "?"} ms`;
}
const stale = (d) => Date.now() - Date.parse(d.generated_at) > 2 * 3600e3;
const text = (o) => ({ content: [{ type: "text", text: JSON.stringify(o, null, 1) }], structuredContent: o });

async function callTool(name, a = {}) {
  const d = await status();
  const meta = { generated_at: d.generated_at, stale: stale(d), methodology: d.methodology };
  if (name === "recommend") {
    if (!a.task) return { isError: true, content: [{ type: "text", text: "task is required" }] };
    const cats = [...new Set(d.tools.map(t => t.task).filter(Boolean))];
    const cat = resolveTask(String(a.task), cats);
    if (!cat) return { isError: true, content: [{ type: "text", text: `Could not map '${a.task}' to a category. Known: ${cats.join(", ")}` }] };
    const ranked = d.tools.filter(t => t.task === cat).map(t => ({ t, s: score(t) })).sort((x, y) => y.s - x.s);
    const healthy = ranked.filter(x => x.t.up && !["major", "critical"].includes(x.t.vendor_status));
    const pick = (healthy.length ? healthy : ranked).slice(0, 3).map(({ t, s }) => ({ name: t.name, kind: t.kind, score: Math.round(s), reason: why(t) }));
    return text({ ...meta, task: a.task, category: cat, top_pick: pick[0] || null, fallbacks: pick.slice(1),
      note: healthy.length ? `Ranked ${ranked.length} providers in '${cat}'. Probes are unauthenticated reachability checks; you still need your own API key.` : `No healthy provider in '${cat}' right now; showing best available.` });
  }
  if (name === "incidents") {
    const h = await history(), days = Math.min(7, Math.max(1, Number(a.days) || 7));
    const since = new Date(Date.parse(h.generated_at) - days * 864e5).toISOString();
    const q = a.name?.toLowerCase();
    const out = [];
    for (const [n, p] of Object.entries(h.providers)) {
      if (q && !n.toLowerCase().includes(q)) continue;
      for (const i of p.incidents) if ((i.end || "9999") >= since) out.push({ provider: n, ...i });
    }
    out.sort((x, y) => (y.start > x.start ? 1 : -1));
    return text({ generated_at: h.generated_at, stale: stale(h), days, count: out.length, incidents: out.slice(0, 100) });
  }
  if (name === "list_tools") {
    const c = a.category?.toLowerCase();
    const tools = d.tools.filter(t => !c || t.category.toLowerCase() === c || t.task?.toLowerCase() === c)
      .map(({ name, category, task, kind, up, latency_ms, vendor_status, uptime_7d_pct }) => ({ name, category, task, kind, up, latency_ms, vendor_status, uptime_7d_pct }));
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
        instructions: "Call recommend(task) to pick a healthy provider before calling an external API, or tool_status(name) to check a specific one; route around tools that are down or whose vendor_status is major/critical. incidents() lists recent outages." });
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

// ---- anonymous usage logging (no IPs) ----
import { DurableObject } from "cloudflare:workers";
const CRAWLERS = /glama|golemreach|pulsemcp|smithery|mcp\.so|mcpmarket|bot|crawl|spider|scan|probe|slurp|headless|python-requests|go-http-client|okhttp|httpx|aiohttp|wget/i;
function uaFamily(ua) {
  const m = ua.match(/^([A-Za-z][\w.\-]*)/); return m ? m[1].slice(0, 40) : (ua ? "other" : "none");
}
function classify(req, ua, client) {
  if (req.headers.get("x-agent-daily-test") || /agent-daily/i.test(ua)) return "own";
  if (CRAWLERS.test(ua) || CRAWLERS.test(client || "")) return "crawler";
  if (/mozilla/i.test(ua) && !client) return "browser";
  return "agent";
}
export class Stats extends DurableObject {
  constructor(ctx, env) { super(ctx, env); this.sql = ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS c (day TEXT, kind TEXT, method TEXT, tool TEXT, arg TEXT, client TEXT, ua TEXT, country TEXT, n INTEGER, last TEXT, PRIMARY KEY(day,kind,method,tool,arg,client,ua,country))"); }
  add(r) { this.sql.exec("INSERT INTO c VALUES (?,?,?,?,?,?,?,?,1,?) ON CONFLICT DO UPDATE SET n=n+1, last=excluded.last",
      r.ts.slice(0, 10), r.kind, r.method, r.tool, r.arg, r.client, r.ua, r.country, r.ts); }
  summary(days) { const since = new Date(Date.now() - days * 864e5).toISOString().slice(0, 10);
    const q = (x) => this.sql.exec(x, since).toArray();
    return { since, by_day_kind: q("SELECT day,kind,SUM(n) n FROM c WHERE day>=? GROUP BY 1,2 ORDER BY 1,2"),
      rows: q("SELECT * FROM c WHERE day>=? ORDER BY day DESC, n DESC LIMIT 500") }; }
}
function record(env, ctx, req, msgs) {
  try {
    const ua = req.headers.get("user-agent") || "", country = req.cf?.country || "??", ts = new Date().toISOString();
    const stub = env.STATS.get(env.STATS.idFromName("global"));
    for (const m of msgs) {
      if (!m || typeof m !== "object") continue;
      const p = m.params || {}, method = String(m.method || "none").slice(0, 40);
      const client = method === "initialize" ? `${p.clientInfo?.name || "?"}/${p.clientInfo?.version || "?"}`.slice(0, 60) : "";
      const tool = method === "tools/call" ? String(p.name || "").slice(0, 40) : "";
      const a = p.arguments || {}, arg = tool ? String(a.category || a.name || "").slice(0, 40) : "";
      const r = { ts, kind: classify(req, ua, client), method, tool, arg, client, ua: uaFamily(ua), country };
      console.log(JSON.stringify({ usage: r }));
      ctx.waitUntil(stub.add(r).catch(() => {}));
    }
  } catch {}
}

export default {
  async scheduled(event, env, ctx) {
    const r = await fetch("https://api.github.com/repos/gregpunch/agent-daily/actions/workflows/check.yml/dispatches", {
      method: "POST", headers: { authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`, accept: "application/vnd.github+json", "user-agent": "agent-daily-cron", "content-type": "application/json" },
      body: JSON.stringify({ ref: "main" }) });
    if (r.status !== 204) throw new Error(`dispatch failed HTTP ${r.status}: ${await r.text()}`);
  },
  async fetch(req, env, ctx) {
    const u = new URL(req.url);
    if (u.pathname === "/stats") {
      if (!env.STATS_KEY || req.headers.get("authorization") !== `Bearer ${env.STATS_KEY}`) return json({ error: "unauthorized" }, 401);
      const stub = env.STATS.get(env.STATS.idFromName("global"));
      return json(await stub.summary(Number(u.searchParams.get("days")) || 7));
    }
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (u.pathname === "/.well-known/mcp/server-card.json") return json(CARD);
    if (u.pathname === "/" ) return json({ ...INFO, mcp: u.origin + "/mcp", data: STATUS_URL });
    if (u.pathname !== "/mcp") return json({ error: "not found" }, 404);
    if (req.method === "GET") return new Response("SSE stream not supported; POST JSON-RPC to /mcp", { status: 405, headers: { Allow: "POST", ...CORS } });
    if (req.method === "DELETE") return new Response(null, { status: 405, headers: CORS });
    if (req.method !== "POST") return new Response(null, { status: 405, headers: CORS });
    let body; try { body = await req.json(); } catch { return json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }, 400); }
    const batch = Array.isArray(body);
    record(env, ctx, req, batch ? body : [body]);
    const out = (await Promise.all((batch ? body : [body]).map(rpc))).filter(Boolean);
    if (!out.length) return new Response(null, { status: 202, headers: CORS });
    return json(batch ? out : out[0]);
  },
};
