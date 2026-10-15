#!/usr/bin/env python3
"""Справжній прогін адмін-флоу на ТЕСТОВОМУ працівнику через ТЕСТОВИЙ Redmine.

Захист: після розбору заявок лишається тільки заявка --ticket і тільки якщо в її імені є прізвище --surname;
усі інші заявки тестового Redmine відкидаються. AD, Google і M365 справжні (креди з живого адмін-флоу),
Redmine тестовий, архівна таблиця на заглушці. Копія флоу після прогону видаляється (або --keep для повтору з тим самим станом).

Запуск: python tests/live_test_admin.py --url https://<n8n> --key-file <файл> --live-id <id адмін-флоу>
        --redmine-cred <id тестового Redmine> --ticket 40247 --surname Testovenko --out <json> [--keep] [--wid <id копії>]
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_linear_tests import Api, ROOT  # noqa: E402

GUARD = """const allowed = %s, surname = %s;
return $input.all().filter(i => String(i.json.id) === String(allowed) &&
  (i.json.pairs || []).some(p => p.some(x => x.toLowerCase() === surname.toLowerCase())));"""


def main():
    ap = argparse.ArgumentParser()
    for k in ("--url", "--key-file", "--live-id", "--redmine-cred", "--ticket", "--surname", "--out"):
        ap.add_argument(k, required=True)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--wid", default="")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    api = Api(a.url, Path(a.key_file).read_text().strip())
    live = api.call("GET", f"/api/v1/workflows/{a.live_id}")
    creds = {k: v for n in live["nodes"] for k, v in (n.get("credentials") or {}).items()}
    wf = json.load(open(ROOT / "workflows" / "admin-offboarding.json", encoding="utf-8"))
    path = "ao-live-" + uuid.uuid4().hex[:10]
    nodes = []
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            continue
        if n["type"] == "n8n-nodes-base.scheduleTrigger":
            n = {"parameters": {"httpMethod": "POST", "path": path, "options": {}}, "type": "n8n-nodes-base.webhook",
                 "typeVersion": 2, "position": n["position"], "id": n["id"], "name": n["name"], "webhookId": str(uuid.uuid4())}
        elif n["type"] == "n8n-nodes-redmine.redmine":
            n["credentials"] = {"redmineApi": {"id": a.redmine_cred, "name": "Redmine TEST account"}}
        elif n["type"] == "n8n-nodes-base.googleSheets":
            n.pop("credentials", None)
            n.pop("retryOnFail", None)
            n.update(type="n8n-nodes-base.code", typeVersion=2,
                     parameters={"jsCode": "return $input.all().map((i, n) => ({ json: { __archive_stub: true }, pairedItem: { item: n } }));"})
        elif n.get("credentials"):
            n["credentials"] = {k: creds[k] for k in n["credentials"]}
        nodes.append(n)
    nodes.append({"parameters": {"jsCode": GUARD % (json.dumps(a.ticket), json.dumps(a.surname))}, "type": "n8n-nodes-base.code",
                  "typeVersion": 2, "position": [550, 600], "id": str(uuid.uuid4()), "name": "TEST GUARD"})
    conns = json.loads(json.dumps(wf["connections"]))
    conns["Code: Parse Tickets"] = {"main": [[{"node": "TEST GUARD", "type": "main", "index": 0}]]}
    conns["TEST GUARD"] = {"main": [[{"node": "Ticket Ready?", "type": "main", "index": 0}]]}
    body = {"name": "[TEMP LIVE-TEST] Admin Offboarding (test user only)", "nodes": nodes, "connections": conns,
            "settings": {"executionOrder": "v1", "timezone": "Europe/Kyiv"}}
    if a.wid:
        old = api.call("GET", f"/api/v1/workflows/{a.wid}")
        hook = next(n for n in old["nodes"] if n["type"] == "n8n-nodes-base.webhook")
        path = hook["parameters"]["path"]
        for n in nodes:
            if n["type"] == "n8n-nodes-base.webhook":
                n["parameters"]["path"], n["webhookId"] = path, hook.get("webhookId")
        api.call("PUT", f"/api/v1/workflows/{a.wid}", body)
        wid = a.wid
    else:
        wid = api.call("POST", "/api/v1/workflows", body)["id"]
    try:
        api.call("POST", f"/api/v1/workflows/{wid}/activate", {})
        time.sleep(2)
        last = (api.call("GET", f"/api/v1/executions?workflowId={wid}&limit=1").get("data") or [{}])[0].get("id")
        api.call("POST", f"/webhook/{path}", {}, raw=True)
        ex = None
        for _ in range(180):
            time.sleep(1)
            d = (api.call("GET", f"/api/v1/executions?workflowId={wid}&limit=1").get("data") or [{}])[0]
            if d.get("id") and d.get("id") != last and d.get("status") not in ("running", "new", "waiting"):
                ex = d
                break
        full = api.call("GET", f"/api/v1/executions/{ex['id']}?includeData=true") if ex else {}
        json.dump(full, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("status", ex and ex.get("status"), "| workflow", wid)
    finally:
        if not a.keep:
            try:
                api.call("POST", f"/api/v1/workflows/{wid}/deactivate", {})
            except Exception:
                pass
            api.call("DELETE", f"/api/v1/workflows/{wid}")
            print("temp workflow deleted", wid)


if __name__ == "__main__":
    main()
