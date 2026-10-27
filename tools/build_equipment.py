"""Збирає workflows/equipment-check.json: щогодинна перевірка техніки працівників, що звільняються, у GLPI.

Креди й адреса GLPI у файлі заглушки (<REDMINE_CRED>, <GLPI_CRED>, <GLPI_URL>), справжні підставляє deploy_equipment.py.
"""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "equipment"
OUT = ROOT / "workflows" / "equipment-check.json"
REDMINE = "n8n-nodes-redmine.redmine"
C_REDMINE = {"redmineApi": {"id": "<REDMINE_CRED>", "name": "Redmine bot account"}}
C_GLPI = {"httpCustomAuth": {"id": "<GLPI_CRED>", "name": "GLPI API (read-only)"}}
GLPI_JS = (ROOT / "src" / "glpi.js").read_text(encoding="utf-8")
nodes, conns = [], {}


def node(name, type_, params, version=1, **extra):
    n = {"parameters": params, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "equipment/" + name)), "name": name,
         "type": type_, "typeVersion": version, "position": [0, 0]}
    n.update(extra)
    nodes.append(n)
    return name


def link(src, dst, out=0):
    m = conns.setdefault(src, {"main": []})["main"]
    while len(m) <= out:
        m.append([])
    m[out].append({"node": dst, "type": "main", "index": 0})


def code(name, file):
    return node(name, "n8n-nodes-base.code", {"jsCode": (SRC / file).read_text(encoding="utf-8").replace("// @@glpi\n", GLPI_JS)}, version=2)


def glpi(name, url, session=True):
    """GET до GLPI (лише читання). App-Token і user_token у кредах n8n «GLPI API (read-only)» (Custom Auth), не в ноді."""
    p = {"method": "GET", "url": url, "authentication": "genericCredentialType", "genericAuthType": "httpCustomAuth",
         "options": {"response": {"response": {"fullResponse": True, "neverError": True}}}}
    if session:
        p.update(sendHeaders=True, headerParameters={"parameters": [
            {"name": "Session-Token", "value": "={{ ($('[GLPI] Open Session').first().json.body || {}).session_token || '' }}"}]})
    return node(name, "n8n-nodes-base.httpRequest", p, version=4.2, onError="continueRegularOutput", credentials=C_GLPI)


STICKY = """## 🖥️ [PROD] Перевірка техніки при звільненні (GLPI)
Щогодини о :30 (до запуску offboarding о 18:00). Лише читання GLPI, у Redmine лише коментарі.

**Заявки:** відкриті в проєкті staff-leavers, трекери 25 (Admin | Leaver) і 41 (GA | Leaver).
**Хто людина в GLPI:** логін AD із заявки або прізвище й ім'я (латиницею й кирилицею, обидва порядки); точний збіг перевіряє код.
**Техніка:** позиції всіх типів, де людина в полі «Користувач». Поле «Контакт» лише підказка.

**Коментар «Перевірка техніки (GLPI): ...»** (його читають флоу offboarding):
* числиться техніка: перелік (тип, назва, інв. №, серійний, статус); заявку не закривають;
* людина є в GLPI, нічого не числиться: «Заборгованості по техніці немає»;
* людини в GLPI немає: лінійний = «Заборгованості по техніці немає» (працюють на своїй техніці), адмін = потрібна перевірка IT;
* кілька кандидатів, лише «Контакт» або помилка: потрібна перевірка IT (помилку для лінійних не пишемо).

Пишемо лише коли висновок змінився. Якщо останнє слово про техніку за людиною з IT, мовчимо.
**Помилки:** Error Workflow."""

node("Every Hour at :30", "n8n-nodes-base.scheduleTrigger",
     {"rule": {"interval": [{"field": "cronExpression", "expression": "30 * * * *"}]}}, version=1.2)
node("[Redmine] Get Open Leaver Tickets", REDMINE, {"operation": "getAll", "returnAll": True,
     "filters": {"project_id": "staff-leavers", "status_id": "open"}, "options": {}}, credentials=C_REDMINE)
code("Code: Parse Tickets", "parse_tickets.js")
node("Loop Over Tickets", "n8n-nodes-base.splitInBatches", {"options": {}}, version=3)
node("[Redmine] Get Ticket History", REDMINE, {"operation": "get", "issueId": "={{ $json.id }}", "include": ["journals"], "options": {}},
     credentials=C_REDMINE)
glpi("[GLPI] Open Session", "<GLPI_URL>/apirest.php/initSession", session=False)
glpi("[GLPI] Find User", "={{ $('Loop Over Tickets').first().json.user_url }}")
glpi("[GLPI] Find Assets", "={{ $('Loop Over Tickets').first().json.assets_url }}")
code("Code: Build Comment", "build_comment.js")
node("Comment Needed?", "n8n-nodes-base.if", {
    "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                   "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "equipment/notify")), "leftValue": "={{ $json.notify }}",
                                   "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                   "combinator": "and"},
    "looseTypeValidation": True, "options": {}}, version=2.2)
node("[Redmine] Add Comment", REDMINE, {"operation": "update", "issueId": "={{ $json.id }}", "notes": "={{ $json.note }}",
     "additionalFields": {}, "options": {}}, credentials=C_REDMINE)
node("Sticky Note: Overview", "n8n-nodes-base.stickyNote", {"content": STICKY, "height": 560, "width": 620, "color": 6})

link("Every Hour at :30", "[Redmine] Get Open Leaver Tickets")
link("[Redmine] Get Open Leaver Tickets", "Code: Parse Tickets")
link("Code: Parse Tickets", "Loop Over Tickets")
link("Loop Over Tickets", "[Redmine] Get Ticket History", 1)   # вихід 0 = done, 1 = loop
link("[Redmine] Get Ticket History", "[GLPI] Open Session")
link("[GLPI] Open Session", "[GLPI] Find User")
link("[GLPI] Find User", "[GLPI] Find Assets")
link("[GLPI] Find Assets", "Code: Build Comment")
link("Code: Build Comment", "Comment Needed?")
link("Comment Needed?", "[Redmine] Add Comment", 0)
link("Comment Needed?", "Loop Over Tickets", 1)
link("[Redmine] Add Comment", "Loop Over Tickets")

import agent_hooks  # noqa: E402  (вхід від агента і запис у спільний аудит)
agent_hooks.add_equipment(nodes, conns, "[Redmine] Get Open Leaver Tickets", "[Redmine] Add Comment", "Loop Over Tickets", "Code: Build Comment")

# Розкладка: два ряди по етапах (заявки, GLPI, коментар). Лише позиції нод.
LAYOUT = [["Every Hour at :30", "[Redmine] Get Open Leaver Tickets", "Code: Parse Tickets", "Loop Over Tickets", "[Redmine] Get Ticket History"],
          ["[GLPI] Open Session", "[GLPI] Find User", "[GLPI] Find Assets", "Code: Build Comment", "Comment Needed?", "[Redmine] Add Comment"],
          [agent_hooks.TRIGGER, "", "", "", "", agent_hooks.LOG]]
POS = {nm: (c, r) for r, row in enumerate(LAYOUT) for c, nm in enumerate(row) if nm}
for n in nodes:
    if n["type"] == "n8n-nodes-base.stickyNote":
        n["position"] = [0, -640]
        continue
    c, r = POS[n["name"]]
    n["position"] = [int(c * 250), int(r * 230)]

wf = {"name": "[PROD] Equipment Check on Offboarding (GLPI) / [PROD] Перевірка техніки при звільненні (GLPI)",
      "nodes": nodes, "connections": conns,
      "settings": {"executionOrder": "v1", "timezone": "Europe/Kyiv", "errorWorkflow": "<ERROR_WORKFLOW_ID>",
                   "callerPolicy": "workflowsFromSameOwner"}}
OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print("built", OUT, len(nodes), "nodes")
