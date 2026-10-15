"""Заливає workflows/admin-offboarding.json у живий адмін-флоу.

Креди підставляються з живої версії за типом, ID таблиці архіву теж; Error Workflow береться з живого флоу,
а якщо там його немає, з --error-from (наприклад, лінійного флоу).

Запуск: python tools/deploy_admin.py --url https://<n8n> --key-file <файл> --id <id адмін-флоу> [--error-from <id>] [--dry]
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDERS = ("<REDMINE_CRED>", "<LDAP_CRED>", "<GADMIN_CRED>", "<GOAUTH_CRED>", "<ENTRA_CRED>", "<SHEETS_CRED>", "<ARCHIVE_SHEET_ID>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--id", required=True)
    ap.add_argument("--error-from", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    H = {"X-N8N-API-KEY": Path(a.key_file).read_text().strip(), "Content-Type": "application/json", "User-Agent": "curl/8.7.1"}
    B = a.url.rstrip("/") + "/api/v1/workflows/"

    def call(method, url, body=None):
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers=H)
        with urllib.request.urlopen(req, timeout=60) as r:
            t = r.read().decode()
            return json.loads(t) if t else {}

    live = call("GET", B + a.id)
    new = json.load(open(ROOT / "workflows" / "admin-offboarding.json", encoding="utf-8"))
    by_type = {k: v for n in live["nodes"] for k, v in (n.get("credentials") or {}).items()}
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
    err = live["settings"].get("errorWorkflow") or (call("GET", B + a.error_from)["settings"].get("errorWorkflow") if a.error_from else "")
    if err:
        settings["errorWorkflow"] = err
    else:
        settings.pop("errorWorkflow")
    left = [p for p in PLACEHOLDERS if p in json.dumps(new, ensure_ascii=False)]
    if missing or left:
        sys.exit(f"не підставлено: {missing} {left}")
    print("nodes:", len(new["nodes"]), "| creds:", sorted({c["name"] for n in new["nodes"] for c in (n.get("credentials") or {}).values()}),
          "| errorWorkflow:", "так" if err else "немає")
    if a.dry:
        return
    call("PUT", B + a.id, {"name": new["name"], "nodes": new["nodes"], "connections": new["connections"], "settings": settings})
    call("POST", B + a.id + "/activate", {})
    r = call("GET", B + a.id)
    print("deployed", r["id"], "active=", r.get("active"), "versionId=", r.get("versionId"), "activeVersionId=", r.get("activeVersionId"))


if __name__ == "__main__":
    main()
