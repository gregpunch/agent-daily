# Agent Daily — Phase 1 tool list

Chosen because agents call them heavily (LLMs, MCP servers, dev, payments, comms, infra, search, knowledge, maps) and because each can be checked free with no API key.

**Check method:** unauthenticated GET to the probe URL with a 10s timeout. We record HTTP code and latency. "Up" means an *expected* code. For auth-gated APIs that's 401/403/422, which proves the edge and API stack respond. Where the vendor runs Atlassian Statuspage we also read `/api/v2/status.json` (`indicator`: none/minor/major/critical). Slack uses `slack-status.com/api/v2.0.0/current`.

| Tool | Category | Probe | Expected | Vendor status JSON |
|---|---|---|---|---|
| OpenAI API | LLM | `https://api.openai.com/v1/models` | 200, 401 | https://status.openai.com/api/v2/status.json |
| Anthropic API | LLM | `https://api.anthropic.com/v1/models` | 200, 401, 404 | https://status.anthropic.com/api/v2/status.json |
| Hugging Face Hub | LLM | `https://huggingface.co/api/models?limit=1` | 200 | — |
| GitHub API | Dev | `https://api.github.com/zen` | 200, 403 | https://www.githubstatus.com/api/v2/status.json |
| GitHub MCP (remote) | MCP | `https://api.githubcopilot.com/mcp/` | 200, 401, 405 | — |
| Linear MCP | MCP | `https://mcp.linear.app/mcp` | 200, 401, 405, 406 | https://linearstatus.com/api/v2/status.json |
| DeepWiki MCP | MCP | `https://mcp.deepwiki.com/mcp` | 200, 400, 405, 406 | — |
| Stripe API | Payments | `https://api.stripe.com/v1/charges` | 401 | — |
| Slack API | Comms | `https://slack.com/api/api.test` | 200 | https://slack-status.com/api/v2.0.0/current |
| Discord API | Comms | `https://discord.com/api/v10/gateway` | 200 | https://discordstatus.com/api/v2/status.json |
| Twilio API | Comms | `https://api.twilio.com/2010-04-01.json` | 200, 401 | https://status.twilio.com/api/v2/status.json |
| Google APIs | Platform | `https://www.googleapis.com/discovery/v1/apis?name=gmail` | 200 | — |
| Cloudflare API | Infra | `https://api.cloudflare.com/client/v4/ips` | 200 | https://www.cloudflarestatus.com/api/v2/status.json |
| Vercel | Infra | `https://api.vercel.com/v2/user` | 401, 403 | https://www.vercel-status.com/api/v2/status.json |
| Supabase | Infra | `https://api.supabase.com/v1/projects` | 401 | https://status.supabase.com/api/v2/status.json |
| Brave Search API | Search | `https://api.search.brave.com/res/v1/web/search?q=test` | 401, 422, 429 | — |
| Serper | Search | `https://google.serper.dev/search` | 400, 401, 403, 405 | — |
| Wikipedia API | Knowledge | `https://en.wikipedia.org/api/rest_v1/page/summary/Agent` | 200 | — |
| OpenStreetMap Nominatim | Maps | `https://nominatim.openstreetmap.org/search?q=Paris&format=json&limit=1` | 200 | — |
| Atlassian (Jira/Confluence) | Productivity | `https://api.atlassian.com/` | 200, 401, 404 | https://status.atlassian.com/api/v2/status.json |

**Limits:** reachability is not correctness. Phase 2 adds keyed functional test tasks (e.g. real search query, real completion) for correctness and cost scores.