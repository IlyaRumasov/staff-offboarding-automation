#!/usr/bin/env python3
"""Сухий прогін на справжніх даних: Redmine (читання) і пошук в AD (читання) справжні,
усе, що змінює дані (LDAP update/rename, Google DELETE, коментарі й закриття в Redmine, Sheets), замінено заглушками.
Тимчасова копія флоу після прогону видаляється. Креди для читання беруться з живого флоу.

Запуск: python tests/dry_run_linear.py --url https://<n8n> --key-file <файл> --live-id <id живого флоу> --out <json>
"""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_linear_tests import Api, ROOT  # noqa: E402

READ_ONLY = {"[Redmine] Get Open Leaver Tickets", "[AD] Search User", "[Google] Check Guest Exists", "[Google] Check API Access"}
WRITERS = {"n8n-nodes-redmine.redmine", "n8n-nodes-base.ldap", "n8n-nodes-base.httpRequest", "n8n-nodes-base.googleSheets"}
ECHO = "return $input.all().map((i, n) => ({ json: { ...i.json, __dry_run: %s }, pairedItem: { item: n } }));"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--live-id", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    api = Api(a.url, Path(a.key_file).read_text().strip())
    live = api.call("GET", f"/api/v1/workflows/{a.live_id}")
    creds = {}
    for n in live["nodes"]:
        for k, v in (n.get("credentials") or {}).items():
            creds[k] = v
    wf = json.load(open(ROOT / "workflows" / "linear-offboarding.json", encoding="utf-8"))
    path = "lo-dry-" + uuid.uuid4().hex[:10]
    nodes = []
    for n in wf["nodes"]:
        if n["type"] == "n8n-nodes-base.stickyNote":
            continue
        if n["type"] == "n8n-nodes-base.scheduleTrigger":
            n = {"parameters": {"httpMethod": "POST", "path": path, "options": {}}, "type": "n8n-nodes-base.webhook",
                 "typeVersion": 2, "position": n["position"], "id": n["id"], "name": n["name"], "webhookId": str(uuid.uuid4())}
        elif n["name"] in READ_ONLY:
            n["credentials"] = {k: creds[k] for k in n["credentials"]}
        elif n["type"] in WRITERS:
            n.pop("credentials", None)
            n.pop("retryOnFail", None)
            n.update(type="n8n-nodes-base.code", typeVersion=2, parameters={"jsCode": ECHO % json.dumps(n["name"])})
        nodes.append(n)
    assert not [n for n in nodes if n["type"] in WRITERS and n["name"] not in READ_ONLY]
    body = {"name": "[TEMP DRY-RUN] Linear Offboarding", "nodes": nodes, "connections": wf["connections"],
            "settings": {"executionOrder": "v1", "timezone": "Europe/Kyiv"}}
    wid = api.call("POST", "/api/v1/workflows", body)["id"]
    try:
        api.call("POST", f"/api/v1/workflows/{wid}/activate", {})
        time.sleep(2)
        api.call("POST", f"/webhook/{path}", {}, raw=True)
        ex = None
        for _ in range(120):
            time.sleep(1)
            d = (api.call("GET", f"/api/v1/executions?workflowId={wid}&limit=1").get("data") or [{}])[0]
            if d.get("id") and d.get("status") not in ("running", "new", "waiting"):
                ex = d
                break
        full = api.call("GET", f"/api/v1/executions/{ex['id']}?includeData=true") if ex else {}
        json.dump(full, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("status", ex and ex.get("status"))
    finally:
        try:
            api.call("POST", f"/api/v1/workflows/{wid}/deactivate", {})
        except Exception:
            pass
        api.call("DELETE", f"/api/v1/workflows/{wid}")
        print("temp workflow deleted", wid)


if __name__ == "__main__":
    main()
