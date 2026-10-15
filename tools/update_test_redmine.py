"""Оновлює заявки в ТЕСТОВОМУ Redmine (коментар і/або статус) через тимчасовий флоу n8n.

Запуск: python tools/update_test_redmine.py --url https://<n8n> --key-file <файл> --cred-id <id креду TEST> --items '<json>' | @<файл.json>
items: [{"id": 40243, "notes": "...", "status_id": "21"}, ...]; з --cf <id> кожен item має ще "cf_value" (значення цього кастомного поля)
"""
import argparse
import json
import sys
import time
import uuid
import urllib.request
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--cred-id", required=True)
    ap.add_argument("--items", required=True)
    ap.add_argument("--cf", default="", help="id кастомного поля для cf_value")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    H = {"X-N8N-API-KEY": Path(a.key_file).read_text().strip(), "Content-Type": "application/json", "User-Agent": "curl/8.7.1"}
    B = a.url.rstrip("/")

    def call(m, p, body=None, raw=False):
        req = urllib.request.Request(B + p, data=json.dumps(body).encode() if body is not None else None, method=m, headers=H)
        with urllib.request.urlopen(req, timeout=120) as r:
            t = r.read().decode()
        return t if raw else (json.loads(t) if t else {})

    items = json.load(open(a.items[1:], encoding="utf-8")) if a.items.startswith("@") else json.loads(a.items)
    path = "rmupd-" + uuid.uuid4().hex[:10]
    wf = {"name": "[TEMP] Update test Redmine", "settings": {"executionOrder": "v1"}, "nodes": [
        {"parameters": {"httpMethod": "POST", "path": path, "options": {}}, "type": "n8n-nodes-base.webhook", "typeVersion": 2,
         "position": [0, 0], "id": str(uuid.uuid4()), "name": "Webhook", "webhookId": str(uuid.uuid4())},
        {"parameters": {"jsCode": "return " + json.dumps(items, ensure_ascii=False) + ".map(j => ({ json: j }));"},
         "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 0], "id": str(uuid.uuid4()), "name": "Items"},
        {"parameters": {"operation": "update", "issueId": "={{ $json.id }}", "notes": "={{ $json.notes || '' }}",
                        "additionalFields": {"status_id": "={{ $json.status_id || undefined }}", "description": "={{ $json.description || undefined }}",
                                             **({"customFields": {"field": [{"id": a.cf, "value": "={{ $json.cf_value }}"}]}} if a.cf else {})},
                        "options": {}},
         "type": "n8n-nodes-redmine.redmine", "typeVersion": 1, "position": [400, 0], "id": str(uuid.uuid4()), "name": "Update",
         "onError": "continueRegularOutput", "credentials": {"redmineApi": {"id": a.cred_id, "name": "Redmine TEST account"}}},
    ], "connections": {"Webhook": {"main": [[{"node": "Items", "type": "main", "index": 0}]]},
                       "Items": {"main": [[{"node": "Update", "type": "main", "index": 0}]]}}}
    wid = call("POST", "/api/v1/workflows", wf)["id"]
    try:
        call("POST", f"/api/v1/workflows/{wid}/activate", {})
        time.sleep(2)
        call("POST", f"/webhook/{path}", {}, raw=True)
        for _ in range(60):
            time.sleep(1)
            d = (call("GET", f"/api/v1/executions?workflowId={wid}&limit=1").get("data") or [{}])[0]
            if d.get("id") and d.get("status") not in ("running", "new", "waiting"):
                break
        full = call("GET", f"/api/v1/executions/{d['id']}?includeData=true")
        out = full["data"]["resultData"]["runData"]["Update"][0]["data"]["main"][0]
        for it, src in zip(out, items):
            err = (it.get("json") or {}).get("error")
            print(src["id"], "ПОМИЛКА: " + str(err)[:150] if err else "ok")
    finally:
        try:
            call("POST", f"/api/v1/workflows/{wid}/deactivate", {})
        except Exception:
            pass
        call("DELETE", f"/api/v1/workflows/{wid}")


if __name__ == "__main__":
    main()
