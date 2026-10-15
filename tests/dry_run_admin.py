#!/usr/bin/env python3
"""Прогін адмін-флоу на ТЕСТОВОМУ Redmine: Redmine справжній тестовий (читання й коментарі),
пошук в AD, Google і M365 справжній (лише читання), усе, що змінює AD/Google/M365 і таблицю, замінено заглушками.
Тимчасова копія флоу після прогону видаляється. Креди для пошуку беруться з живого адмін-флоу.

Запуск: python tests/dry_run_admin.py --url https://<n8n> --key-file <файл> --live-id <id адмін-флоу>
        --redmine-cred <id креду тестового Redmine> --out <json> [--keep-state]
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_linear_tests import Api, ROOT  # noqa: E402

READ_ONLY = {"[AD] Search User", "[Google] Find User", "[Google] Find Drive Recipient", "[M365] Search User"}
TEST_REDMINE = {"[Redmine] Get Open Leaver Tickets", "[Redmine] Get Ticket History", "[Redmine] Update Ticket", "[Redmine] Comment Missing Data"}
STUB = {"[AD] Disable Account": {"dn": "", "result": "success"}, "[AD] Move to Fired OU": {"dn": "", "result": "success"},
        "[Google] Suspend User": {"statusCode": 200, "body": {"suspended": True}},
        "[Google] Transfer Drive": {"statusCode": 200, "body": {"overallTransferStatusCode": "dry-run"}},
        "[M365] Delete User": {"statusCode": 204, "body": ""}, "[Sheets] Add to Archive": {}}
ECHO = "return $input.all().map((i, n) => ({ json: { ...%s, __dry_run: true }, pairedItem: { item: n } }));"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--live-id", required=True)
    ap.add_argument("--redmine-cred", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--wid", default="", help="оновити наявну тимчасову копію замість нової (зберігає static data)")
    ap.add_argument("--keep", action="store_true", help="не видаляти копію (для повторного прогону з тим самим станом)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    api = Api(a.url, Path(a.key_file).read_text().strip())
    live = api.call("GET", f"/api/v1/workflows/{a.live_id}")
    creds = {}
    for n in live["nodes"]:
        for k, v in (n.get("credentials") or {}).items():
            creds[k] = v
    wf = json.load(open(ROOT / "workflows" / "admin-offboarding.json", encoding="utf-8"))
    path = "ao-dry-" + uuid.uuid4().hex[:10]
    nodes = []
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            continue
        if n["type"] == "n8n-nodes-base.scheduleTrigger":
            n = {"parameters": {"httpMethod": "POST", "path": path, "options": {}}, "type": "n8n-nodes-base.webhook",
                 "typeVersion": 2, "position": n["position"], "id": n["id"], "name": n["name"], "webhookId": str(uuid.uuid4())}
        elif n["name"] in TEST_REDMINE:
            n["credentials"] = {"redmineApi": {"id": a.redmine_cred, "name": "Redmine TEST account"}}
        elif n["name"] in READ_ONLY:
            n["credentials"] = {k: creds[k] for k in n["credentials"]}
        elif n["name"] in STUB:
            n.pop("credentials", None)
            n.pop("retryOnFail", None)
            n.update(type="n8n-nodes-base.code", typeVersion=2, parameters={"jsCode": ECHO % json.dumps(STUB[n["name"]])})
        elif n.get("credentials"):
            sys.exit(f"вузол з кредами не класифіковано: {n['name']}")
        nodes.append(n)
    body = {"name": "[TEMP DRY-RUN] Admin Offboarding (test Redmine)", "nodes": nodes, "connections": wf["connections"],
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
