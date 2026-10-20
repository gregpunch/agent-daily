# Agent Daily: Tool Reliability Index (prototype)

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
