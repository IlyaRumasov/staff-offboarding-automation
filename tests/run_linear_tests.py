#!/usr/bin/env python3
"""Тести флоу offboarding лінійного персоналу на заглушках.

Скрипт збирає тестову копію флоу: Cron замінено на Webhook, усі зовнішні вузли (Redmine, LDAP,
Google, Sheets) замінено Code-заглушками з відповідями з cases_linear.json. Копія імпортується
в n8n неактивною, активується лише на час тесту, після тесту видаляється. Реальні AD, Google,
Redmine і таблиця не викликаються.

Запуск:
    python tests/run_linear_tests.py --url https://<ваш-n8n> --key-file <файл з ключем API>
"""
import argparse
import copy
import json
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTERNAL = {"n8n-nodes-redmine.redmine", "n8n-nodes-base.ldap", "n8n-nodes-base.httpRequest", "n8n-nodes-base.googleSheets"}
STUB = """const NAME = %s;
const all = $('Webhook').first().json.body.stubs || {};
const inp = $input.first() ? $input.first().json : {};
let s = all[NAME];
if (s && s.__by_ticket) {
  let tid = '';
  try { tid = String($('Loop Over Tickets').first().json.id); } catch (e) {}
  s = s.__by_ticket[tid];
}
if (s && s.__by_login) {
  let login = '';
  try { const L = $('Loop Over Tickets').first().json; login = L.login || L.sn; } catch (e) {}
  s = s.__by_login[login];
}
if (s && s.__throw) throw new Error(s.__throw);
if (s === undefined) s = { ...inp, __stub: NAME };
return (Array.isArray(s) ? s : [s]).map(j => ({ json: j, pairedItem: { item: 0 } }));"""
RESET = """const body = $input.first().json.body;
const st = $getWorkflowStaticData('global');
if (body.reset) { for (const k of Object.keys(st)) delete st[k]; }
return [{ json: {} }];"""


class Api:
    def __init__(self, url, key):
        self.url, self.key = url.rstrip("/"), key

    def call(self, method, path, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method, headers={
            "X-N8N-API-KEY": self.key, "Content-Type": "application/json", "User-Agent": "curl/8.7.1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
        return txt if raw else (json.loads(txt) if txt else {})


def build_harness(wf, path):
    w = copy.deepcopy(wf)
    trig = next(n["name"] for n in w["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger")
    first = w["connections"][trig]["main"][0][0]["node"]
    w["name"] = "[TEST-HARNESS] " + w["name"][:60]
    nodes = []
    for n in w["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote" or n["name"] == trig:
            continue
        n.pop("credentials", None)
        n.pop("retryOnFail", None)
        if n["type"] in EXTERNAL:
            n.update(type="n8n-nodes-base.code", typeVersion=2, parameters={"jsCode": STUB % json.dumps(n["name"])})
        nodes.append(n)
    nodes.append({"parameters": {"httpMethod": "POST", "path": path, "options": {}}, "type": "n8n-nodes-base.webhook",
                  "typeVersion": 2, "position": [-400, 400], "id": str(uuid.uuid4()), "name": "Webhook", "webhookId": str(uuid.uuid4())})
    nodes.append({"parameters": {"jsCode": RESET}, "type": "n8n-nodes-base.code", "typeVersion": 2,
                  "position": [-200, 400], "id": str(uuid.uuid4()), "name": "Reset State"})
    w["nodes"] = nodes
    conns = {k: v for k, v in w["connections"].items() if k != trig}
    conns["Webhook"] = {"main": [[{"node": "Reset State", "type": "main", "index": 0}]]}
    conns["Reset State"] = {"main": [[{"node": first, "type": "main", "index": 0}]]}
    w["connections"] = conns
    w["settings"] = {"executionOrder": "v1", "timezone": "Europe/Kyiv"}
    return w


def render(obj):
    kyiv = datetime.now(timezone(timedelta(hours=3)))  # Europe/Kyiv літом; тести не біля півночі
    t = json.dumps(obj, ensure_ascii=False)
    for k, d in (("$YESTERDAY", -1), ("$TODAY", 0), ("$TOMORROW", 1)):
        t = t.replace(k, (kyiv + timedelta(days=d)).strftime("%Y-%m-%d"))
    return json.loads(t)


def items(run, node):
    """Елементи виходу вузла. «Вузол::поле=значення» залишає лише елементи з таким значенням поля."""
    cond = None
    if "::" in node:
        node, cond = node.split("::", 1)
    out = []
    for r in run.get(node, []):
        for o in (r.get("data") or {}).get("main", []) or []:
            out.extend(i["json"] for i in (o or []))
    if cond:
        field, val = cond.split("=", 1)
        out = [i for i in out if str(i.get(field)).lower() == val.lower()]
    return out


def match(item, spec):
    for k, want in spec.items():
        got = item.get(k)
        if isinstance(want, str) and want.startswith("~"):
            if want[1:] not in str(got):
                return False
        elif got != want:
            return False
    return True


def check(step, run):
    errs = []
    for n in step.get("expect", []):
        if n not in run:
            errs.append(f"вузол не відпрацював: {n}")
    for n in step.get("not_expect", []):
        if n in run:
            errs.append(f"вузол не мав відпрацювати: {n}")
    for n, cnt in step.get("counts", {}).items():
        got = len(items(run, n))
        if got != cnt:
            errs.append(f"{n}: елементів {got}, очікувалось {cnt}")
    for n, specs in step.get("has", {}).items():
        got = items(run, n)
        for spec in specs:
            if not any(match(i, spec) for i in got):
                errs.append(f"{n}: немає елемента {spec} (є: {[{k: str(i.get(k))[:70] for k in spec} for i in got]})")
    return errs


def run_step(api, wid, path, body, last):
    api.call("POST", f"/webhook/{path}", body, raw=True)
    for _ in range(60):
        time.sleep(0.5)
        d = (api.call("GET", f"/api/v1/executions?workflowId={wid}&limit=1").get("data") or [{}])[0]
        if d.get("id") and d.get("id") != last and d.get("status") not in ("running", "new", "waiting"):
            return d
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--workflow", default=str(ROOT / "workflows" / "linear-offboarding.json"))
    ap.add_argument("--cases", default=str(Path(__file__).with_name("cases_linear.json")))
    ap.add_argument("--only", default="")
    ap.add_argument("--keep", action="store_true", help="не видаляти тестову копію")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    api = Api(a.url, Path(a.key_file).read_text().strip())
    wf = json.load(open(a.workflow, encoding="utf-8"))
    cases = json.load(open(a.cases, encoding="utf-8"))
    if a.only:
        cases = [c for c in cases if a.only in c["name"]]
    path = "lo-test-" + uuid.uuid4().hex[:10]
    wid = api.call("POST", "/api/v1/workflows", build_harness(wf, path))["id"]
    failed = 0
    try:
        api.call("POST", f"/api/v1/workflows/{wid}/activate", {})
        time.sleep(2)
        last = (api.call("GET", f"/api/v1/executions?workflowId={wid}&limit=1").get("data") or [{}])[0].get("id")
        for raw in cases:
            c = render(raw)
            steps = c.get("steps") or [c]
            errs = []
            for i, st in enumerate(steps):
                ex = run_step(api, wid, path, {"reset": i == 0, "stubs": st.get("stubs", {})}, last)
                if not ex:
                    errs.append(f"крок {i + 1}: виконання не з'явилось")
                    break
                last = ex["id"]
                rd = api.call("GET", f"/api/v1/executions/{ex['id']}?includeData=true")["data"]["resultData"]
                e = check(st, rd["runData"])
                if rd.get("error"):
                    e.append("помилка виконання: " + str(rd["error"].get("message"))[:160])
                errs += [(f"крок {i + 1}: " if len(steps) > 1 else "") + x for x in e]
            print(("PASS " if not errs else "FAIL ") + c["name"])
            for e in errs:
                print("     -", e)
            failed += bool(errs)
    finally:
        if not a.keep:
            try:
                api.call("POST", f"/api/v1/workflows/{wid}/deactivate", {})
            except Exception:
                pass
            api.call("DELETE", f"/api/v1/workflows/{wid}")
    print(f"\nПройдено {len(cases) - failed} з {len(cases)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
