"""Заливає workflows/linear-offboarding.json у живий флоу, підставляючи з живої версії креди, ID таблиці архіву і Error Workflow.

Запуск: python tools/deploy_linear.py --url https://<n8n> --key-file <файл> --id <id флоу> [--dry]
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--id", required=True)
    ap.add_argument("--dry", action="store_true", help="лише показати, що буде залито")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    key = Path(a.key_file).read_text().strip()
    H = {"X-N8N-API-KEY": key, "Content-Type": "application/json", "User-Agent": "curl/8.7.1"}
    U = a.url.rstrip("/") + "/api/v1/workflows/" + a.id

    def call(method, url, body=None):
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers=H)
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read().decode()
            return json.loads(t) if t else {}

    live = call("GET", U)
    new = json.load(open(ROOT / "workflows" / "linear-offboarding.json", encoding="utf-8"))
    by_type = {}
    for n in live["nodes"]:
        for k, v in (n.get("credentials") or {}).items():
            by_type[k] = v
    sheet = next(n for n in live["nodes"] if n["type"] == "n8n-nodes-base.googleSheets")["parameters"]["documentId"]["value"]
    missing = []
    for n in new["nodes"]:
        for k in list((n.get("credentials") or {}).keys()):
            if k in by_type:
                n["credentials"][k] = by_type[k]
            else:
                missing.append(f"{n['name']}:{k}")
        if n["type"] == "n8n-nodes-base.googleSheets":
            n["parameters"]["documentId"]["value"] = sheet
    settings = dict(new["settings"])
    settings["errorWorkflow"] = live["settings"].get("errorWorkflow", "")
    if not settings["errorWorkflow"]:
        settings.pop("errorWorkflow")
    text = json.dumps(new, ensure_ascii=False)
    left = [p for p in ("<REDMINE_CRED>", "<LDAP_CRED>", "<GW_CRED>", "<SHEETS_CRED>", "<ARCHIVE_SHEET_ID>") if p in text]
    if missing or left:
        sys.exit(f"не підставлено: {missing} {left}")
    print("nodes:", len(new["nodes"]), "| creds:", sorted({c["name"] for n in new["nodes"] for c in (n.get("credentials") or {}).values()}))
    if a.dry:
        return
    body = {"name": new["name"], "nodes": new["nodes"], "connections": new["connections"], "settings": settings}
    r = call("PUT", U, body)
    call("POST", U + "/activate", {})
    r = call("GET", U)
    print("deployed", r["id"], "active=", r.get("active"), "versionId=", r.get("versionId"), "activeVersionId=", r.get("activeVersionId"))


if __name__ == "__main__":
    main()
