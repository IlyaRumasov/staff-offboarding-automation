"""Коротко показує виконання флоу з JSON-файлу: вузли, помилки, рішення по заявках і тексти коментарів."""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open(sys.argv[1], encoding="utf-8"))
rd = d["data"]["resultData"]
print("error:", (rd.get("error") or {}).get("message"))


def items(n):
    return [i.get("json", i) for r in rd["runData"].get(n, []) for o in (r.get("data") or {}).get("main", []) or [] for i in (o or [])]


for n, runs in rd["runData"].items():
    errs = [r["error"].get("message") for r in runs if r.get("error")]
    print(f"  {n}: runs={len(runs)} items={len(items(n))}", errs or "")
for n in ("Code: Parse Tickets", "Code: Parse Tickets"):
    for j in items(n):
        print("PARSE", j.get("id"), j.get("action"), j.get("reason", ""), j.get("pairs", ""), (j.get("drive") or {}).get("mode", ""))
for j in items("Code: Build Report"):
    print(f"\n=== #{j.get('id')} close={j.get('close')} notify={j.get('notify')}\n{j.get('note')}")
for n in ("[Redmine] Comment Missing Data",):
    for j in items(n):
        print(f"\n=== MISSING #{j.get('id')}")
