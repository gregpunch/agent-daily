# Agent Daily: is this tool up right now?

**A free, hourly reliability index for the APIs and MCP servers AI agents call**: OpenAI, Anthropic, GitHub (API + MCP), Stripe, Slack, Cloudflare, Brave/Serper search, Linear and DeepWiki MCP, and more (20 tools).

Built for agent builders. Check before your agent calls a tool, fall back when a tool is down, and stop burning retries on outages.

- Status page: https://gregpunch.github.io/agent-daily/
- Machine-readable: https://gregpunch.github.io/agent-daily/status.json
- Agent guide: https://gregpunch.github.io/agent-daily/llms.txt

## Consume status.json
```python
import requests
s = requests.get("https://gregpunch.github.io/agent-daily/status.json", timeout=5).json()
tool = next(t for t in s["tools"] if t["name"] == "OpenAI API")
if not tool["up"] or tool["vendor_status"] in ("major", "critical"):
    ...  # route to a fallback provider
```
Fields: `schema_version`, `generated_at` (UTC), `summary.{up,total}`, and `tools[]` with `name, category, up, http_status, latency_ms, vendor_status, uptime_24h_pct, checks_24h, error`. Data is refreshed hourly; treat it as stale if older than about 2h. Please cache.

**Limits:** these are reachability checks only (an expected HTTP code), not correctness or quality tests. There is a single probe location.


A free public status page for 20 tools AI agents depend on. This is Phase 1, a two-week validation.

## Run locally
```
python3 check.py   # probe all tools -> results.db (SQLite)
python3 build.py   # render site/index.html
```
Files: `tools.json` (config), `tools.md` (list + method), `check.py`, `build.py`, `site/` (static output), `preview.png`.

## Deploy plan (free tiers)
**Recommended: GitHub Actions + GitHub Pages ($0).**
1. Push this folder to a public GitHub repo.
2. Add `.github/workflows/check.yml` with `schedule: cron: "0 * * * *"` (hourly). Steps: checkout, `pip install requests`, `python check.py && python build.py`, commit `results.db` back (or store it as an artifact), then deploy `site/` with `actions/deploy-pages`.
3. Turn on Pages (source: GitHub Actions). Public repos get unlimited Actions minutes.

**Alternative: Cloudflare Worker cron + D1 + Pages ($0).** Port `check.py` to a Worker `scheduled()` handler (free tier: 100k requests/day, cron triggers included). Store rows in D1 (free 5 GB), and render the page or serve JSON from the Worker or Pages. This option is the better base for the paid MCP/API later.

## Estimated monthly cost
| Item | Cost |
|---|---|
| GitHub Actions + Pages (public repo) or Cloudflare free tier | $0 |
| Domain (optional, e.g. agentdaily.dev) | ~$1–1.25/mo ($12–15/yr) |
| Paid-API functional tests (Phase 2 only) | $0 now; cap $30–50 |
| **Phase 1 total** | **$0–2/mo** |
