#!/usr/bin/env python3
"""Build site/llm/ (leaderboard.json, models/<id>.json, html) from llm.db. Empty state if no data."""
import json, sqlite3, pathlib, datetime, statistics, html, shutil
D = pathlib.Path(__file__).parent; OUT = D/"site/llm"; (OUT/"models").mkdir(parents=True, exist_ok=True)
CFG = json.load(open(D/"llm/models.json"))
now = datetime.datetime.now(datetime.timezone.utc)
def iso(dt): return dt.isoformat(timespec="seconds")
rows = []
if (D/"llm.db").exists():
    db = sqlite3.connect(D/"llm.db"); db.row_factory = sqlite3.Row
    try: rows = [dict(r) for r in db.execute("SELECT * FROM probes WHERE ts>=? ORDER BY ts", (iso(now-datetime.timedelta(days=7)),))]
    except sqlite3.OperationalError: rows = []
    rows = [r for r in rows if r["ts"] not in CFG.get("excluded_runs", {})]
def fid(m): return m.replace("/", "__")
def med(xs): xs = [x for x in xs if x is not None]; return int(statistics.median(xs)) if xs else None
ERR = ["rate_limit", "content_filter", "timeout", "wrong_answer", "server_error", "client_error", "network"]
by = {}
for r in rows: by.setdefault(r["id"], []).append(r)
since24 = iso(now-datetime.timedelta(hours=24))
stats = []
for mid, rs in by.items():
    r24 = [r for r in rs if r["ts"] >= since24] or []
    if not r24: continue
    good = [r for r in r24 if r["ok"]]
    costs = [r["cost"] for r in r24 if r["cost"] is not None]
    stats.append({"id": mid, "file": fid(mid), "model": rs[-1]["model"], "provider": rs[-1]["provider"], "route": rs[-1]["route"],
        "probes_24h": len(r24), "correct_pct_24h": round(100*len(good)/len(r24), 1),
        "uptime_pct_24h": round(100*sum(1 for r in r24 if r["error_type"] in (None, "wrong_answer"))/len(r24), 1),
        "p50_ttft_ms": med(r["ttft_ms"] for r in good), "p50_total_ms": med(r["total_ms"] for r in good),
        "cost_per_1k_calls_usd": round(1000*statistics.mean(costs), 4) if costs else None,
        "last": {"ts": rs[-1]["ts"], "ok": bool(rs[-1]["ok"]), "error_type": rs[-1]["error_type"]}})
def prank(vals, v):  # 100 = fastest
    if v is None: return 0.0
    vs = [x for x in vals if x is not None]
    if len(vs) <= 1: return 100.0
    return round(100*sum(1 for x in vs if x > v)/(len(vs)-1), 1)
tt = [s["p50_ttft_ms"] for s in stats]; to = [s["p50_total_ms"] for s in stats]
for s in stats:
    s["speed_score"] = round((prank(tt, s["p50_ttft_ms"]) + prank(to, s["p50_total_ms"]))/2, 1)
    s["correctness_score"] = s["correct_pct_24h"]
    s["score"] = round(0.6*s["correctness_score"] + 0.4*s["speed_score"], 1)
stats.sort(key=lambda s: -s["score"])
for i, s in enumerate(stats): s["rank"] = i+1
last_ts = rows[-1]["ts"] if rows else None
LB = {"schema_version": "1.0", "generated_at": iso(now), "last_probe_at": last_ts, "status": "ok" if stats else "awaiting_first_probe",
      "prompt": "Reply with exactly the word pong", "expected": "pong", "cadence": "every 15 minutes",
      "scoring": "score = 0.6*correct_pct_24h + 0.4*speed_score; speed_score = mean percentile rank (100 = fastest) of p50 TTFT and p50 total time among ranked models",
      "models": stats}
json.dump(LB, open(OUT/"leaderboard.json", "w"), indent=1)
for old in (OUT/"models").glob("*.json"): old.unlink()
def buckets(rs, start, step, n):
    out = []
    for i in range(n):
        a, b = iso(start+i*step), iso(start+(i+1)*step)
        x = [r for r in rs if a <= r["ts"] < b]; g = [r for r in x if r["ok"]]
        out.append({"t": a, "n": len(x), "correct_pct": round(100*len(g)/len(x), 1) if x else None,
                    "p50_ttft_ms": med(r["ttft_ms"] for r in g), "p50_total_ms": med(r["total_ms"] for r in g)})
    return out
for s in stats:
    rs = by[s["id"]]; r24 = [r for r in rs if r["ts"] >= since24]
    eb = lambda xs: {e: sum(1 for r in xs if r["error_type"] == e) for e in ERR}
    h = now.replace(minute=0, second=0, microsecond=0)
    json.dump({**s, "generated_at": iso(now),
        "chart_24h": buckets(rs, h-datetime.timedelta(hours=23), datetime.timedelta(hours=1), 24),
        "chart_7d": buckets(rs, h-datetime.timedelta(hours=6*27), datetime.timedelta(hours=6), 28),
        "errors_24h": eb(r24), "errors_7d": eb(rs),
        "last_50": [{k: r[k] for k in ("ts", "ok", "reply", "http", "error_type", "detail", "ttft_ms", "total_ms", "tok_in", "tok_out", "cost")} for r in reversed(rs[-50:])]},
        open(OUT/"models"/f"{s['file']}.json", "w"), indent=1)
for f in ("index.html", "model.html", "style.css"): shutil.copy(D/"llm"/f, OUT/f)
models_list = "".join(f"<li><code>{html.escape(m)}</code></li>" for m in CFG["openrouter"])
direct_list = "".join(f"<li>{d['provider']}: <code>{d['model']}</code> (runs only if {d['key']} is configured)</li>" for d in CFG["direct"])
(OUT/"methods.html").write_text((D/"llm/methods.tmpl.html").read_text().replace("{{MODELS}}", models_list).replace("{{DIRECT}}", direct_list)
    .replace("{{MAXT}}", str(CFG["max_tokens"])).replace("{{OVERRIDES}}", ", ".join(f"<code>{html.escape(k)}</code> ({html.escape(json.dumps(v['reasoning']))})" for k,v in CFG.get("overrides",{}).items()) or "none").replace("{{EXCLUDED}}", "".join(f"<li>{html.escape(k)} UTC: {html.escape(v)}</li>" for k,v in CFG.get("excluded_runs",{}).items()) or "<li>None</li>").replace("{{CAP}}", str(CFG["monthly_cap_usd"])))
print(f"llm: {len(stats)} models ranked, {len(rows)} probes in 7d, status={LB['status']}")
