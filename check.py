#!/usr/bin/env python3
"""Agent Daily checker: probes tools, stores results in SQLite."""
import os, json, sqlite3, time, datetime, requests, pathlib
D = pathlib.Path(__file__).parent
UA = {"User-Agent": "AgentDaily-StatusBot/0.1 (+https://agentdaily.dev)"}
db = sqlite3.connect(D/"results.db")
db.execute("""CREATE TABLE IF NOT EXISTS checks(ts TEXT, name TEXT, cat TEXT, up INT,
 http INT, latency_ms INT, vendor TEXT, error TEXT)""")
def vendor_status(t):
    try:
        if t.get("slack"):
            j = requests.get(t["slack"], headers=UA, timeout=10).json(); return j.get("status","?")
        if t.get("status"):
            j = requests.get(t["status"], headers=UA, timeout=10).json()
            return j["status"]["indicator"]  # none/minor/major/critical
    except Exception as e: return "unavailable"
    return None
ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
def probe(t):
    http=lat=None; err=None; r=None
    try:
        s=time.perf_counter(); h=dict(UA)
        if t.get("auth")=="github" and os.environ.get("GITHUB_TOKEN"): h["Authorization"]="Bearer "+os.environ["GITHUB_TOKEN"]
        r=requests.get(t["probe"], headers=h, timeout=10, allow_redirects=True)
        lat=int((time.perf_counter()-s)*1000); http=r.status_code
    except Exception as e: err=type(e).__name__
    up = int(http in t["ok"]) if http else 0
    if http and not up: err=f"unexpected HTTP {http}"
    if up and t.get("expect_login"):
        try: login=r.json().get("login")
        except Exception: login=None
        if login!=t["expect_login"]: up=0; err=f"login mismatch: {login}"
    return t,up,http,lat,vendor_status(t),err
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(16) as ex:
    for t,up,http,lat,v,err in ex.map(probe, json.load(open(D/"tools.json"))):
        db.execute("INSERT INTO checks VALUES(?,?,?,?,?,?,?,?)",(ts,t["name"],t["cat"],up,http,lat,v,err))
        print(f"{t['name']:28} up={up} http={http} {lat}ms vendor={v} {err or ''}")
db.commit()
