"""Заливає workflows/equipment-check.json у n8n: створює новий флоу (без --id) або оновлює наявний (--id).

Креди Redmine і Error Workflow беруться з живого лінійного флоу (--from), креди GLPI з --glpi-cred або з наявної версії,
адреса GLPI з --glpi-url або з наявної версії. Флоу вмикається лише з --activate.

Запуск: python tools/deploy_equipment.py --url https://<n8n> --key-file <файл> --from <id лінійного флоу>
        [--id <id флоу перевірки>] [--glpi-cred <id>] [--glpi-url <адреса>] [--activate] [--dry]
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDERS = ("<REDMINE_CRED>", "<GLPI_CRED>", "<GLPI_URL>", "<AUDIT_TABLE>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--from", dest="src", required=True, help="id живого флоу, звідки взяти креди Redmine і Error Workflow")
    ap.add_argument("--id", default="", help="id наявного флоу перевірки техніки (без нього створюється новий)")
    ap.add_argument("--glpi-cred", default="")
    ap.add_argument("--glpi-url", default="")
    ap.add_argument("--audit-table", default="", help="id Data Table спільного аудиту агента (якщо в живій версії її ще немає)")
    ap.add_argument("--activate", action="store_true")
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

    src = call("GET", B + a.src)
    cur = call("GET", B + a.id) if a.id else {"nodes": []}
    new = json.load(open(ROOT / "workflows" / "equipment-check.json", encoding="utf-8"))
    by_type = {k: v for w in (src, cur) for n in w["nodes"] for k, v in (n.get("credentials") or {}).items()}
    if a.glpi_cred:
        by_type["httpCustomAuth"] = {"id": a.glpi_cred, "name": "GLPI API (read-only)"}
    cur_glpi = next((n for n in cur["nodes"] if n["name"] == "[GLPI] Open Session"), None)
    glpi_url = (a.glpi_url or (cur_glpi["parameters"]["url"].split("/apirest.php")[0] if cur_glpi else "")).rstrip("/")
    if glpi_url:
        new = json.loads(json.dumps(new, ensure_ascii=False).replace("<GLPI_URL>", glpi_url))
    audit = a.audit_table or next((n["parameters"]["dataTableId"]["value"] for w in (cur, src) for n in w["nodes"]
                                   if n["type"] == "n8n-nodes-base.dataTable"), "")
    for n in new["nodes"]:
        if n["type"] == "n8n-nodes-base.dataTable" and audit:
            n["parameters"]["dataTableId"]["value"] = audit
    missing = []
    for n in new["nodes"]:
        for k in list((n.get("credentials") or {}).keys()):
            if k in by_type:
                n["credentials"][k] = by_type[k]
            else:
                missing.append(f"{n['name']}:{k}")
    settings = dict(new["settings"])
    err = src["settings"].get("errorWorkflow", "")
    if err:
        settings["errorWorkflow"] = err
    else:
        settings.pop("errorWorkflow")
    left = [p for p in PLACEHOLDERS if p in json.dumps(new, ensure_ascii=False)]
    if missing or left:
        sys.exit(f"не підставлено: {missing} {left}")
    print("nodes:", len(new["nodes"]), "| creds:", sorted({c["name"] for n in new["nodes"] for c in (n.get("credentials") or {}).values()}),
          "| errorWorkflow:", "так" if err else "немає", "|", "оновлення " + a.id if a.id else "новий флоу")
    if a.dry:
        return
    body = {"name": new["name"], "nodes": new["nodes"], "connections": new["connections"], "settings": settings}
    wid = call("PUT", B + a.id, body)["id"] if a.id else call("POST", B, body)["id"]
    if a.activate:
        call("POST", B + wid + "/activate", {})
    r = call("GET", B + wid)
    print("deployed", r["id"], "active=", r.get("active"), "versionId=", r.get("versionId"))


if __name__ == "__main__":
    main()
