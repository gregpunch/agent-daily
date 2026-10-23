#!/usr/bin/env python3
"""Render static site/index.html from results.db."""
import sqlite3, pathlib, html, datetime, json
D=pathlib.Path(__file__).parent; db=sqlite3.connect(D/"results.db")
last=db.execute("SELECT max(ts) FROM checks").fetchone()[0]
rows=db.execute("SELECT name,cat,up,http,latency_ms,vendor,error FROM checks WHERE ts=? ORDER BY cat,name",(last,)).fetchall()
since=(datetime.datetime.fromisoformat(last)-datetime.timedelta(hours=24)).isoformat()
upt={n:(u,c) for n,u,c in db.execute("SELECT name,sum(up),count(*) FROM checks WHERE ts>=? GROUP BY name",(since,))}
VC={"none":"ok","minor":"warn","major":"bad","critical":"bad","ok":"ok","active":"warn"}
tr=""
for n,c,u,h,l,v,e in rows:
    s,k=upt.get(n,(0,0)); pct=f"{100*s/k:.0f}% <small>({k} checks)</small>" if k else "—"
    vtxt={"none":"Operational","ok":"Operational"}.get(v,v or "n/a")
    tr+=f"<tr><td><span class='dot {'ok' if u else 'bad'}'></span>{html.escape(n)}</td><td>{c}</td><td>{'Up' if u else 'Down'}</td><td>{l if l is not None else '—'} ms</td><td>{h or html.escape(e or '')}</td><td><span class='pill {VC.get(v,'na')}'>{html.escape(vtxt)}</span></td><td>{pct}</td></tr>"
BASE="https://gregpunch.github.io/agent-daily/"
LD=json.dumps({"@context":"https://schema.org","@type":"Dataset","name":"Agent Daily Tool Reliability Index","description":"Hourly reachability, latency and vendor status for APIs and MCP servers used by AI agents.","url":BASE,"license":"https://creativecommons.org/licenses/by/4.0/","isAccessibleForFree":True,"temporalCoverage":last,"distribution":[{"@type":"DataDownload","encodingFormat":"application/json","contentUrl":BASE+"status.json"}],"creator":{"@type":"Organization","name":"Agent Daily"}})
upn=sum(r[2] for r in rows)
page=f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Agent Daily — Tool Reliability Index</title>
<meta name=description content="Hourly reachability and vendor status for 20 APIs and MCP servers AI agents depend on. Machine-readable at status.json.">
<link rel=canonical href="{BASE}"><link rel=alternate type=application/json href="{BASE}status.json">
<meta property=og:title content="Agent Daily — Tool Reliability Index"><meta property=og:type content=website><meta property=og:url content="{BASE}">
<meta property=og:description content="Live status of APIs and MCP servers for AI agents. JSON at /status.json, guide at /llms.txt.">
<script type="application/ld+json">{LD}</script><style>
body{{font-family:system-ui,sans-serif;background:#0b0f17;color:#e6e9ef;margin:0;padding:32px}}
.wrap{{max-width:1000px;margin:auto}}h1{{margin:0;font-size:28px}}.sub{{color:#8b93a7;margin:6px 0 20px}}
.banner{{background:#13261b;border:1px solid #1f6f3f;padding:14px 18px;border-radius:10px;margin-bottom:20px}}
table{{width:100%;border-collapse:collapse;background:#111827;border-radius:10px;overflow:hidden}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #1f2937;font-size:14px}}th{{color:#8b93a7;font-weight:600}}
.dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:8px}}.dot.ok{{background:#22c55e}}.dot.bad{{background:#ef4444}}
.pill{{padding:2px 8px;border-radius:999px;font-size:12px}}.pill.ok{{background:#14532d}}.pill.warn{{background:#713f12}}.pill.bad{{background:#7f1d1d}}.pill.na{{background:#374151}}
footer{{color:#6b7280;font-size:12px;margin-top:16px}}</style></head><body><div class=wrap>
<h1>Agent Daily</h1><div class=sub>Live reliability index for the tools and APIs AI agents depend on.</div>
<div class=banner><b>{upn}/{len(rows)}</b> tools reachable · last check {last} UTC</div>
<table><tr><th>Tool</th><th>Category</th><th>Probe</th><th>Latency</th><th>HTTP</th><th>Vendor status</th><th>24h uptime</th></tr>{tr}</table>
<footer>Probes are unauthenticated reachability checks; "Up" means the endpoint answered with an expected code (401 counts as up for auth-gated APIs). Vendor status comes from public status-page JSON. Methodology: see tools.md. Agents: use <a style="color:#93c5fd" href="status.json">status.json</a> · <a style="color:#93c5fd" href="llms.txt">llms.txt</a>.</footer>
</div></body></html>"""
(D/"site").mkdir(exist_ok=True); (D/"site/index.html").write_text(page); print("wrote site/index.html")

tools=[]
for n,c,u,h,l,v,e in rows:
    k_s,k=upt.get(n,(0,0))
    tools.append({"name":n,"category":c,"up":bool(u),"http_status":h,"latency_ms":l,"vendor_status":v,"error":e,"uptime_24h_pct":round(100*k_s/k,1) if k else None,"checks_24h":k})
json.dump({"schema_version":"1.0","generated_at":last,"update_cadence":"hourly","methodology":"Unauthenticated reachability probe; up = expected HTTP code. Not a correctness test.","summary":{"up":upn,"total":len(rows)},"tools":tools},open(D/"site/status.json","w"),indent=1)
(D/"site/llms.txt").write_text(f"""# Agent Daily

> Hourly reliability index of 20 APIs and MCP servers that AI agents depend on (OpenAI, Anthropic, GitHub, Stripe, Slack, Cloudflare, search APIs, public MCP servers and more). Free, no key required.

## How agents should use it
- GET {BASE}status.json before choosing or calling a tool. Per tool: up (bool), http_status, latency_ms, vendor_status (from the vendor's status page: none=operational, minor, major, critical; null if none published), uptime_24h_pct, checks_24h.
- Top-level: schema_version, generated_at (UTC ISO 8601), summary.up/total.
- If generated_at is older than ~2 hours, treat the data as stale.
- Please cache; fetch at most once every few minutes.

## MCP server
- Remote MCP (Streamable HTTP, no auth, read-only): https://agent-daily.agentdaily.workers.dev/mcp
- Tools: list_tools(category?) and tool_status(name). Both are backed by status.json with a 5-minute cache.

## Update cadence
Checks run hourly (GitHub Actions cron); the page and JSON are regenerated each run.

## Methodology limits
- Reachability only: "up" means the endpoint answered with an expected HTTP code (401/403/422 count as up for auth-gated APIs). It does NOT test correctness, quality, or rate limits.
- Single probe location (GitHub-hosted runner, US). Latency is indicative.
- Vendor status is self-reported by vendors.

## Links
- [Human status page]({BASE})
- [Tool list and check method](https://github.com/gregpunch/agent-daily/blob/main/tools.md)
- [Source](https://github.com/gregpunch/agent-daily)
""")
(D/"site/robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {BASE}sitemap.xml\n")
(D/"site/sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+"".join(f"<url><loc>{BASE}{p}</loc><lastmod>{last[:10]}</lastmod><changefreq>hourly</changefreq></url>" for p in ["","status.json","llms.txt"])+"</urlset>\n")
print("wrote status.json llms.txt robots.txt sitemap.xml")
