#!/usr/bin/env python3
"""Agent Daily LLM live probe: one 'pong' call per model, streamed, stored in llm.db."""
import os, json, time, sqlite3, datetime, pathlib, re, requests
from concurrent.futures import ThreadPoolExecutor
D = pathlib.Path(__file__).parent
CFG = json.load(open(D/"llm/models.json"))
PROMPT = "Reply with exactly the word pong"
MAXT, TO = CFG["max_tokens"], CFG["timeout_s"]
db = sqlite3.connect(D/"llm.db")
db.execute("""CREATE TABLE IF NOT EXISTS probes(ts TEXT, id TEXT, model TEXT, provider TEXT, route TEXT, ok INT, reply TEXT,
 http INT, error_type TEXT, detail TEXT, ttft_ms INT, total_ms INT, tok_in INT, tok_out INT, cost REAL)""")
ORK = os.environ.get("OPENROUTER_API_KEY")
def norm(s): return re.sub(r"\.$", "", (s or "").strip()).strip().lower()
spent = db.execute("SELECT coalesce(sum(cost),0) FROM probes WHERE ts>=?", ((datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=30)).isoformat(),)).fetchone()[0]
if spent >= CFG["monthly_cap_usd"]:
    print(f"monthly cap reached (${spent:.2f}); skipping"); raise SystemExit(0)
PRICES = {}
try: PRICES = {m["id"]: m["pricing"] for m in requests.get("https://openrouter.ai/api/v1/models", timeout=20).json()["data"]}
except Exception as e: print("pricing fetch failed", e)
def price(ref, ti, to):
    p = PRICES.get(ref)
    return None if not p or ti is None else ti*float(p["prompt"]) + (to or 0)*float(p["completion"])

def classify(http, txt, finish):
    t = (txt or "").lower()
    if http == 429 or "rate limit" in t: return "rate_limit"
    if finish == "content_filter" or "moderation" in t or "content filter" in t or "safety" in t: return "content_filter"
    if http and http >= 500: return "server_error"
    return "client_error"

def stream(url, headers, body, parse):
    """parse(obj, st) updates st dict with text/usage/finish. Returns result dict."""
    st = {"text": "", "tin": None, "tout": None, "cost": None, "finish": None, "err": None}
    t0 = time.perf_counter(); ttft = None; http = None
    try:
        with requests.post(url, headers=headers, json=body, stream=True, timeout=(10, TO)) as r:
            http = r.status_code
            if r.status_code != 200:
                txt = r.text[:300]
                return dict(http=http, error_type=classify(http, txt, None), detail=txt, ttft=None, total=int((time.perf_counter()-t0)*1000), **st)
            for line in r.iter_lines(decode_unicode=True):
                if time.perf_counter()-t0 > TO: raise requests.Timeout()
                if not line or not line.startswith("data:"): continue
                data = line[5:].strip()
                if data == "[DONE]": break
                try: o = json.loads(data)
                except Exception: continue
                before = st["text"]; parse(o, st)
                if ttft is None and st["text"] != before: ttft = int((time.perf_counter()-t0)*1000)
    except requests.Timeout:
        return dict(http=http, error_type="timeout", detail=f">{TO}s", ttft=ttft, total=TO*1000, **st)
    except Exception as e:
        return dict(http=http, error_type="network", detail=type(e).__name__, ttft=ttft, total=int((time.perf_counter()-t0)*1000), **st)
    total = int((time.perf_counter()-t0)*1000)
    if st["err"]: return dict(http=http, error_type=classify(http, st["err"], st["finish"]), detail=st["err"][:300], ttft=ttft, total=total, **st)
    if st["finish"] == "content_filter": return dict(http=http, error_type="content_filter", detail="finish_reason=content_filter", ttft=ttft, total=total, **st)
    ok = norm(st["text"]) == "pong"
    return dict(http=http, error_type=None if ok else "wrong_answer", detail=None, ttft=ttft, total=total, **st)

def p_oa(o, st):  # OpenAI/OpenRouter chunk
    if o.get("error"): st["err"] = json.dumps(o["error"])[:300]
    for c in o.get("choices") or []:
        st["text"] += (c.get("delta") or {}).get("content") or ""
        if c.get("finish_reason"): st["finish"] = c["finish_reason"]
    u = o.get("usage")
    if u: st["tin"], st["tout"], st["cost"] = u.get("prompt_tokens"), u.get("completion_tokens"), u.get("cost", st["cost"])

def p_an(o, st):
    t = o.get("type")
    if t == "message_start": st["tin"] = o["message"]["usage"].get("input_tokens")
    elif t == "content_block_delta": st["text"] += o["delta"].get("text", "")
    elif t == "message_delta":
        st["tout"] = o.get("usage", {}).get("output_tokens"); st["finish"] = o.get("delta", {}).get("stop_reason")
    elif t == "error": st["err"] = json.dumps(o.get("error"))[:300]

def p_gm(o, st):
    for c in o.get("candidates") or []:
        for p in (c.get("content") or {}).get("parts") or []: st["text"] += p.get("text", "")
        if c.get("finishReason") == "SAFETY": st["finish"] = "content_filter"
    u = o.get("usageMetadata")
    if u: st["tin"], st["tout"] = u.get("promptTokenCount"), u.get("candidatesTokenCount")

MSG = [{"role": "user", "content": PROMPT}]
jobs = []
if ORK:
    for m in CFG["openrouter"]:
        jobs.append((m, m, m.split("/")[0], "openrouter", lambda m=m: stream("https://openrouter.ai/api/v1/chat/completions",
            {"Authorization": f"Bearer {ORK}", "HTTP-Referer": "https://gregpunch.github.io/agent-daily/llm/", "X-Title": "Agent Daily LLM probe"},
            {"model": m, "messages": MSG, "temperature": 0, "max_tokens": MAXT, "stream": True, "usage": {"include": True},
             "reasoning": {"effort": "low", "exclude": True}}, p_oa), m))
else: print("OPENROUTER_API_KEY missing: skipping OpenRouter probes")
for d in CFG["direct"]:
    k = os.environ.get(d["key"])
    if not k: print(f"{d['key']} missing: skipping direct {d['provider']}"); continue
    mid = f"direct/{d['provider']}/{d['model']}"
    if d["provider"] == "openai":
        f = lambda d=d, k=k: stream("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {k}"},
            {"model": d["model"], "messages": MSG, "max_completion_tokens": MAXT, "stream": True, "stream_options": {"include_usage": True}}, p_oa)
    elif d["provider"] == "anthropic":
        f = lambda d=d, k=k: stream("https://api.anthropic.com/v1/messages", {"x-api-key": k, "anthropic-version": "2023-06-01"},
            {"model": d["model"], "messages": MSG, "max_tokens": MAXT, "temperature": 0, "stream": True}, p_an)
    else:
        f = lambda d=d, k=k: stream(f"https://generativelanguage.googleapis.com/v1beta/models/{d['model']}:streamGenerateContent?alt=sse", {"x-goog-api-key": k},
            {"contents": [{"parts": [{"text": PROMPT}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": MAXT}}, p_gm)
    jobs.append((mid, d["model"], d["provider"], "direct", f, d["price_ref"]))
if not jobs: print("no keys available; nothing to probe"); raise SystemExit(0)
ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
def run(j):
    mid, model, prov, route, f, ref = j; r = f()
    cost = r["cost"] if r["cost"] is not None else price(ref, r["tin"], r["tout"])
    return mid, model, prov, route, r, cost
with ThreadPoolExecutor(8) as ex:
    for mid, model, prov, route, r, cost in ex.map(run, jobs):
        ok = int(r["error_type"] is None)
        db.execute("INSERT INTO probes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (ts, mid, model, prov, route, ok, (r["text"] or "")[:200],
            r["http"], r["error_type"], r["detail"], r["ttft"], r["total"], r["tin"], r["tout"], cost))
        print(f"{mid:40} ok={ok} {r['error_type'] or ''} ttft={r['ttft']} total={r['total']} reply={r['text'][:20]!r} cost={cost}")
db.commit()
