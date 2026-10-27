#!/usr/bin/env python3
"""Перевірка доробок для агента на ТЕСТОВОМУ Redmine: виклик «обробити зараз» для однієї заявки і запис у спільний аудит.

Лінійний флоу запускається як під-воркфлоу з {ticket_id}. Усе, що змінює AD і Google, і архів у Sheets замінено заглушками;
Redmine — тестовий (коментар і закриття справжні), пошук в AD і перевірка Google — лише читання; аудит — тестова Data Table.
Створюються дві заявки: обробитись має лише та, чий id передано. Тимчасові флоу видаляються, заявки закриваються.

python tests/test_agent_hooks.py --url https://<n8n> --key-file <файл> --redmine-cred <id> --ldap-cred <id> --google-cred <id> --table <id>
"""
import argparse, json, sys, time, uuid, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUB = "return $input.all().map((i, n) => ({ json: { ...i.json, __stub: %s }, pairedItem: { item: n } }));"


def main():
    ap = argparse.ArgumentParser()
    for k in ("url", "key-file", "redmine-cred", "ldap-cred", "google-cred", "table"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    H = {"X-N8N-API-KEY": Path(a.key_file).read_text().strip(), "Content-Type": "application/json", "User-Agent": "curl/8.7.1"}
    B = a.url.rstrip("/")

    def call(m, p, body=None):
        r = urllib.request.Request(B + p, data=json.dumps(body).encode() if body is not None else None, method=m, headers=H)
        t = urllib.request.urlopen(r, timeout=180).read().decode()
        return json.loads(t) if t else {}

    def temp(name, nodes, conn, activate=False):
        wid = call("POST", "/api/v1/workflows", {"name": name, "nodes": nodes, "connections": conn, "settings": {"executionOrder": "v1", "timezone": "Europe/Kyiv"}})["id"]
        if activate:
            call("POST", f"/api/v1/workflows/{wid}/activate", {})
        return wid

    def run(wid, path):
        call("POST", f"/api/v1/workflows/{wid}/activate", {})
        time.sleep(2)
        urllib.request.urlopen(urllib.request.Request(B + f"/webhook/{path}", data=b"{}", method="POST", headers=H), timeout=180).read()
        for _ in range(180):
            time.sleep(1)
            d = (call("GET", f"/api/v1/executions?workflowId={wid}&limit=1").get("data") or [{}])[0]
            if d.get("id") and d.get("status") not in ("running", "new", "waiting"):
                return call("GET", f"/api/v1/executions/{d['id']}?includeData=true")["data"]["resultData"]

    RM = {"redmineApi": {"id": a.redmine_cred, "name": "Redmine TEST account"}}
    rm = lambda name, params, x: {"parameters": params, "type": "n8n-nodes-redmine.redmine", "typeVersion": 1, "position": [x, 0],
                                  "id": str(uuid.uuid4()), "name": name, "credentials": RM}
    hook = lambda path: {"parameters": {"httpMethod": "POST", "path": path, "options": {}}, "type": "n8n-nodes-base.webhook", "typeVersion": 2,
                         "position": [0, 0], "id": str(uuid.uuid4()), "name": "Webhook", "webhookId": str(uuid.uuid4())}
    created = []
    # 1. дві тестові заявки «GA | Leaver» з датою звільнення вчора
    y = (datetime.now(timezone(timedelta(hours=3))) - timedelta(days=1)).strftime("%Y-%m-%d")
    items = [{"subject": f"GA | Leaver | Test Guest {n} | {y}", "description": f"ГА - Test Guest{n}\nAD - test.guest.{n}", "due": y} for n in (31, 33)]
    p1 = "ah-seed-" + uuid.uuid4().hex[:8]
    seed = [hook(p1), {"parameters": {"jsCode": "return " + json.dumps(items, ensure_ascii=False) + ".map(j => ({ json: j }));"},
                       "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 0], "id": str(uuid.uuid4()), "name": "Items"},
            rm("Create", {"operation": "create", "projectId": "169", "subject": "={{ $json.subject }}",
                          "additionalFields": {"tracker_id": "41", "description": "={{ $json.description }}", "due_date": "={{ $json.due }}",
                                               "start_date": "={{ $json.due }}",
                                               "customFields": {"field": [{"id": "15", "value": "+380000000000"}, {"id": "17", "value": "Ukraine"}]}},
                          "options": {}}, 400)]
    sid = temp("[TEMP] agent hooks seed", seed, {"Webhook": {"main": [[{"node": "Items", "type": "main", "index": 0}]]},
                                                 "Items": {"main": [[{"node": "Create", "type": "main", "index": 0}]]}})
    created.append(sid)
    rd = run(sid, p1)
    ids = [((i["json"].get("issue") or i["json"]).get("id")) for i in rd["runData"]["Create"][0]["data"]["main"][0]]
    print("заявки:", ids, "| обробити зараз лише", ids[0])
    try:
        # 2. тимчасова копія лінійного флоу як під-воркфлоу
        wf = json.load(open(ROOT / "workflows" / "linear-offboarding.json", encoding="utf-8"))
        nodes = []
        for n in wf["nodes"]:
            if n["type"] in ("n8n-nodes-base.stickyNote", "n8n-nodes-base.scheduleTrigger"):
                continue
            if n["type"] == "n8n-nodes-redmine.redmine":
                n["credentials"] = RM
                if n["name"] == "[Redmine] Get Open Leaver Tickets":
                    n["parameters"].setdefault("filters", {})["project_id"] = "169"
            elif n["type"] == "n8n-nodes-base.ldap" and n["parameters"].get("operation") in (None, "search"):
                n["credentials"] = {"ldap": {"id": a.ldap_cred, "name": "LDAP"}}
            elif n["name"] in ("[Google] Check API Access", "[Google] Check Guest Exists"):
                n["credentials"] = {"googleApi": {"id": a.google_cred, "name": "Google SA"}}
            elif n["type"] == "n8n-nodes-base.dataTable":
                n["parameters"]["dataTableId"]["value"] = a.table
            elif n["type"] in ("n8n-nodes-base.ldap", "n8n-nodes-base.httpRequest", "n8n-nodes-base.googleSheets"):
                n.pop("credentials", None); n.pop("retryOnFail", None)
                n.update(type="n8n-nodes-base.code", typeVersion=2, parameters={"jsCode": STUB % json.dumps(n["name"])})
            nodes.append(n)
        conn = {k: v for k, v in wf["connections"].items() if k != "Every Day 18:00"}
        sub = temp("[TEMP] linear offboarding (agent hooks test)", nodes, conn, activate=True)
        created.append(sub)
        # 3. виклик «обробити зараз» з {ticket_id}
        p2 = "ah-call-" + uuid.uuid4().hex[:8]
        caller = [hook(p2), {"parameters": {"assignments": {"assignments": [{"id": "t", "name": "ticket_id", "value": ids[0], "type": "number"}]}, "options": {}},
                             "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": [200, 0], "id": str(uuid.uuid4()), "name": "Ticket"},
                  {"parameters": {"source": "database", "workflowId": {"__rl": True, "mode": "id", "value": sub}, "mode": "once",
                                  "options": {"waitForSubWorkflow": True}}, "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2,
                   "position": [400, 0], "id": str(uuid.uuid4()), "name": "Process Now"}]
        cid = temp("[TEMP] agent hooks caller", caller, {"Webhook": {"main": [[{"node": "Ticket", "type": "main", "index": 0}]]},
                                                         "Ticket": {"main": [[{"node": "Process Now", "type": "main", "index": 0}]]}})
        created.append(cid)
        rd = run(cid, p2)
        print("виклик:", "помилка " + rd["error"]["message"] if rd.get("error") else "ок")
        sub_ex = (call("GET", f"/api/v1/executions?workflowId={sub}&limit=1").get("data") or [{}])[0]
        srd = call("GET", f"/api/v1/executions/{sub_ex['id']}?includeData=true")["data"]["resultData"] if sub_ex.get("id") else {}
        rn = srd.get("runData", {})
        parsed = [i["json"].get("id") for b in (rn.get("Code: Parse Tickets", [{}])[0].get("data", {}).get("main") or []) for i in (b or [])]
        print("розбір віддав заявки:", parsed)
        for nm in ("[Redmine] Update Ticket", "[Data Table] Log Result", "[Data Table] Log Missing Data", "[Sheets] Add to Archive"):
            r = rn.get(nm)
            print(f"  {nm}: {'виконано' if r else '-'}" + (f" ПОМИЛКА {r[0]['error']['message']}" if r and r[0].get("error") else ""))
        logged = [i["json"] for i in ((rn.get("[Data Table] Log Result") or [{}])[0].get("data", {}).get("main") or [[]])[0]]
        print("  рядок аудиту:", [{k: x.get(k) for k in ("ticket_id", "kind", "logins", "outcome")} for x in logged])
        # 4. стан заявок
        p3 = "ah-st-" + uuid.uuid4().hex[:8]
        st = [hook(p3)] + [rm(f"I{i}", {"operation": "get", "issueId": str(i), "include": ["journals"], "options": {}}, 300) for i in ids]
        sid2 = temp("[TEMP] agent hooks state", st, {"Webhook": {"main": [[{"node": f"I{i}", "type": "main", "index": 0} for i in ids]]}})
        created.append(sid2)
        rd = run(sid2, p3)
        for i in ids:
            o = rd["runData"][f"I{i}"][0]["data"]["main"][0][0]["json"]
            o = o.get("issue", o)
            notes = [j["notes"] for j in o.get("journals", []) if j.get("notes")]
            print(f"  #{i}: {o['status']['name']} | {notes[-1][:120] if notes else 'без коментарів'}")
    finally:
        for w in created:
            try: call("POST", f"/api/v1/workflows/{w}/deactivate", {})
            except Exception: pass
            call("DELETE", f"/api/v1/workflows/{w}")
        print("тимчасові флоу видалено:", len(created))


if __name__ == "__main__":
    main()
