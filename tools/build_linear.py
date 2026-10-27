"""Збирає workflows/linear-offboarding.json з коду в src/linear/.

Секретів і ID у файлі немає: ID таблиці архіву = <ARCHIVE_SHEET_ID>, креди підставляє deploy.py з живої версії.
"""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "linear"
OUT = ROOT / "workflows" / "linear-offboarding.json"

REDMINE = "n8n-nodes-redmine.redmine"
nodes, conns = [], {}


EQUIPMENT_JS = (ROOT / "src" / "equipment_state.js").read_text(encoding="utf-8")


def js(name):
    return (SRC / name).read_text(encoding="utf-8").replace("// @@equipment\n", EQUIPMENT_JS)


def node(name, type_, params, x, y, version=1, **extra):
    n = {"parameters": params, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "linear/" + name)), "name": name,
         "type": type_, "typeVersion": version, "position": [x, y]}
    n.update(extra)
    nodes.append(n)
    return name


def link(src, dst, out=0):
    m = conns.setdefault(src, {"main": []})["main"]
    while len(m) <= out:
        m.append([])
    m[out].append({"node": dst, "type": "main", "index": 0})


def if_true(name, left, x, y):
    return node(name, "n8n-nodes-base.if", {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)), "leftValue": left, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "looseTypeValidation": True, "options": {}}, x, y, version=2.2)


def code(name, file, x, y):
    return node(name, "n8n-nodes-base.code", {"jsCode": js(file)}, x, y, version=2)


def redmine_note(name, x, y, close=False):
    p = {"operation": "update", "issueId": "={{ $json.id }}", "notes": "={{ $json.note }}",
         "additionalFields": {"status_id": "17"} if close else {}, "options": {}}
    return node(name, REDMINE, p, x, y, credentials={"redmineApi": {"id": "<REDMINE_CRED>", "name": "Redmine bot account"}})


LDAP_CRED = {"ldap": {"id": "<LDAP_CRED>", "name": "LDAP service account"}}
STICKY = """## 🛡️ [PROD] Offboarding лінійного персоналу (GA | Leaver)
Блокування в AD, видалення гостя з Google Workspace, архів у Google Sheets, звіт у Redmine.

**Розклад:** щодня о 18:00 (Europe/Kyiv).

**Логіка**
1. Redmine: відкриті заявки трекера 41, усі сторінки.
2. Розбір: AD-логін (рядок `AD -` в описі або поле «AD login»; якщо порожньо, пошук в AD за ПІБ з рядка `ГА -` або теми, латиницею за КМУ-2010, лише при єдиному збігу імені та прізвища), дата звільнення (Termination date → Due date → тема). Дата в майбутньому: чекаємо. Немає логіна чи дати: один коментар у заявку, заявка відкрита.
3. По кожній заявці: пошук у всьому AD за sAMAccountName.
   * в `OU=AllUsers`: блокування (прапорець ACCOUNTDISABLE, інші не чіпаємо) і перенос в `OU=Уволенные` (LDAP-ноди, креди в n8n);
   * вже заблокований в «Уволенные»: AD пропускаємо;
   * логін є, а в AD немає: перевірка (читання) гостя Google; гостя теж немає = імовірно видалено автоматично за неактивність, закриваємо з поясненням; гість є = коментар;
   * кілька, поза AllUsers, не знайдено за ПІБ, помилка: коментар, заявка відкрита.
4. Google: на початку запуску перевірка доступу до API (читання одного користувача домену). Для цього сервісного акаунта неіснуючий гість дає 403, а не 404 (перевірено 14.10.2026), тому 403 = «гостя немає» лише якщо перевірка доступу пройшла.
   DELETE гостя. 2xx або «гостя немає»: закриваємо заявку (статус 17) зі звітом і пишемо в архів. Інша відповідь: коментар, повтор наступного дня.
5. Техніка: останній коментар про техніку в заявці (IT або флоу «Перевірка техніки (GLPI)»). Числиться техніка: доступи закриваємо, заявку ні.

**Без спаму:** коментар про ту саму проблему пишеться один раз (static data флоу).
**Помилки:** Error Workflow."""

T = node("Every Day 18:00", "n8n-nodes-base.scheduleTrigger",
         {"rule": {"interval": [{"field": "cronExpression", "expression": "0 18 * * *"}]}}, 0, 400, version=1.2)
HC = node("[Google] Check API Access", "n8n-nodes-base.httpRequest", {
    "method": "GET", "url": "https://admin.googleapis.com/admin/directory/v1/users?domain=tenant.example.org&maxResults=1",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "googleApi",
    "options": {"response": {"response": {"fullResponse": True, "neverError": True}}}},
    110, 600, version=4.2, onError="continueRegularOutput",
    credentials={"googleApi": {"id": "<GW_CRED>", "name": "Google service account (guests)"}})
F = node("[Redmine] Get Open Leaver Tickets", REDMINE,
         {"operation": "getAll", "returnAll": True, "filters": {"tracker_id": "41", "status_id": "open"}, "options": {}},
         220, 400, credentials={"redmineApi": {"id": "<REDMINE_CRED>", "name": "Redmine bot account"}})
P = code("Code: Parse Tickets", "parse_leavers.js", 440, 400)
R = if_true("Ticket Ready?", "={{ $json.action === 'process' }}", 660, 400)
# Фільтр дослівним шаблоном із фіксованими слотами: нода екранує підставлені значення, а фільтр цілком із виразу ламається.
FILTER = ("=(&(objectClass=user)(|" + "".join("(sn={{ $json.ldap_sn[%d] }})" % i for i in range(4))
          + "".join("(sAMAccountName={{ $json.ldap_sam[%d] }})" % i for i in range(16)) + "))")
MC = redmine_note("[Redmine] Comment Missing Data", 880, 600)
LP = node("Loop Over Tickets", "n8n-nodes-base.splitInBatches", {"options": {}}, 880, 300, version=3)
S = node("[AD] Search User", "n8n-nodes-base.ldap", {
    "baseDN": "DC=example,DC=com", "searchFor": "custom",
    "customFilter": FILTER,
    "returnAll": True, "options": {"scope": "sub", "attributes": ["userAccountControl", "sAMAccountName", "givenName", "sn", "displayName", "cn", "whenCreated"]}},
    1100, 300, alwaysOutputData=True, credentials=LDAP_CRED)
D = code("Code: Decide AD Action", "decide_ad.js", 1320, 300)
SW = node("Route by AD Status", "n8n-nodes-base.switch", {
    "rules": {"values": [
        {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                        "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, "sw" + v)), "leftValue": "={{ $json.ad_status }}",
                                        "rightValue": v, "operator": {"type": "string", "operation": "equals"}}],
                        "combinator": "and"}, "renameOutput": True, "outputKey": v}
        for v in ("disable", "already_done", "not_found")]},
    "options": {"fallbackOutput": "extra", "renameFallbackOutput": "problem"}}, 1540, 300, version=3.2)
UP = node("[AD] Disable Account", "n8n-nodes-base.ldap", {
    "operation": "update", "dn": "={{ $json.dn }}",
    "attributes": {"replace": [{"id": "userAccountControl", "value": "={{ $json.new_uac }}"}]}},
    1760, 120, onError="continueErrorOutput", credentials=LDAP_CRED)
MV = node("[AD] Move to Fired OU", "n8n-nodes-base.ldap", {
    "operation": "rename", "dn": "={{ $('Code: Decide AD Action').item.json.dn }}",
    "targetDn": "={{ $('Code: Decide AD Action').item.json.target_dn }}"},
    1980, 120, onError="continueErrorOutput", credentials=LDAP_CRED)
GW = node("[Google] Delete Guest", "n8n-nodes-base.httpRequest", {
    "method": "DELETE",
    "url": "=https://admin.googleapis.com/admin/directory/v1/users/{{ encodeURIComponent($('Code: Decide AD Action').item.json.guest_email) }}",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "googleApi",
    "options": {"response": {"response": {"fullResponse": True, "neverError": True}}}},
    2200, 300, version=4.2, onError="continueRegularOutput",
    credentials={"googleApi": {"id": "<GW_CRED>", "name": "Google service account (guests)"}})
GC = node("[Google] Check Guest Exists", "n8n-nodes-base.httpRequest", {
    "method": "GET",
    "url": "=https://admin.googleapis.com/admin/directory/v1/users/{{ encodeURIComponent($('Code: Decide AD Action').item.json.guest_email) }}",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "googleApi",
    "options": {"response": {"response": {"fullResponse": True, "neverError": True}}}},
    1980, 760, version=4.2, onError="continueRegularOutput",
    credentials={"googleApi": {"id": "<GW_CRED>", "name": "Google service account (guests)"}})
TH = node("[Redmine] Get Ticket History", REDMINE, {"operation": "get", "issueId": "={{ $('Code: Decide AD Action').first().json.id }}",
          "include": ["journals"], "options": {}}, 2310, 300,
          credentials={"redmineApi": {"id": "<REDMINE_CRED>", "name": "Redmine bot account"}})
FR = code("Code: Build Report", "report.js", 2420, 300)
NU = if_true("Update Ticket Needed?", "={{ $json.close || $json.notify }}", 2640, 300)
UT = node("[Redmine] Update Ticket", REDMINE, {"operation": "update", "issueId": "={{ $json.id }}", "notes": "={{ $json.note }}",
          "additionalFields": {"status_id": "={{ $json.close ? '17' : undefined }}"}, "options": {}}, 2860, 200,
          credentials={"redmineApi": {"id": "<REDMINE_CRED>", "name": "Redmine bot account"}})
AR = if_true("Add to Archive?", "={{ $('Update Ticket Needed?').item.json.close }}", 3080, 200)
SH = node("[Sheets] Add to Archive", "n8n-nodes-base.googleSheets", {
    "operation": "append",
    "documentId": {"__rl": True, "value": "<ARCHIVE_SHEET_ID>", "mode": "id"},
    "sheetName": {"__rl": True, "value": "gid=0", "mode": "list"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Date": "={{ $('Update Ticket Needed?').item.json.leaver_date }}",
        "Login": "={{ $('Update Ticket Needed?').item.json.login }}",
        "Ticket ID": "={{ $('Update Ticket Needed?').item.json.id }}",
        "Google guest account ": "={{ $('Update Ticket Needed?').item.json.guest_email }}"},
        "matchingColumns": [], "schema": [
            {"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True, "type": "string",
             "canBeUsedToMatch": True, "removed": False} for c in ("Date", "Login", "Ticket ID", "Google guest account ")],
        "attemptToConvertTypes": False, "convertFieldsToString": False},
    "options": {}}, 3300, 100, version=4, retryOnFail=True,
    credentials={"googleSheetsOAuth2Api": {"id": "<SHEETS_CRED>", "name": "Google Sheets account"}})
PN = code("Code: Build Problem Note", "problem_note.js", 1980, 500)
node("Sticky Note: Overview", "n8n-nodes-base.stickyNote",
     {"content": STICKY, "height": 640, "width": 640, "color": 6}, 0, -360)

link(T, HC); link(HC, F); link(F, P); link(P, R)
link(R, LP, 0); link(R, MC, 1)
link(LP, S, 1)                      # вихід 0 = done, 1 = loop
link(S, D); link(D, SW)
link(SW, UP, 0); link(SW, GW, 1); link(SW, GC, 2); link(SW, PN, 3)
link(UP, MV, 0); link(UP, PN, 1)
link(MV, GW, 0); link(MV, PN, 1)
link(GW, TH); link(GC, TH); link(TH, FR)
link(FR, NU); link(PN, NU)
link(NU, UT, 0); link(NU, LP, 1)
link(UT, AR)
link(AR, SH, 0); link(AR, LP, 1)
link(SH, LP)


import agent_hooks  # noqa: E402  (вхід від агента і запис у спільний аудит)
agent_hooks.add(nodes, conns, "linear", "offboarding_linear", "[Google] Check API Access", "[Redmine] Update Ticket",
                "Add to Archive?", "[Redmine] Comment Missing Data", "Ticket Ready?")

# Розкладка сіткою по етапах: розбір заявок, AD, Google, звіт і оновлення заявки. Лише позиції нод.
LAYOUT_ROWS = [
    ["Every Day 18:00", "[Google] Check API Access", "[Redmine] Get Open Leaver Tickets", "Code: Parse Tickets", "Ticket Ready?",
     "Loop Over Tickets", "[AD] Search User"],
    ["Code: Decide AD Action", "Route by AD Status", "[AD] Disable Account", "[AD] Move to Fired OU", "[Google] Delete Guest",
     "[Redmine] Get Ticket History", "Code: Build Report", "Update Ticket Needed?"],
]
LAYOUT_EXTRA = {"[Redmine] Comment Missing Data": (4, 0.75), "Code: Build Problem Note": (2, 2), "[Google] Check Guest Exists": (4, 2),
                "[Redmine] Update Ticket": (7, 2), "Add to Archive?": (7, 3), "[Sheets] Add to Archive": (8, 3),
                agent_hooks.TRIGGER: (0, 0.75), agent_hooks.LOG: (8, 2), agent_hooks.LOG_MISSING: (5, 0.75)}

POS = {nm: (c, r) for r, row in enumerate(LAYOUT_ROWS) for c, nm in enumerate(row)}
POS.update(LAYOUT_EXTRA)
for n in nodes:
    if n["type"] == "n8n-nodes-base.stickyNote":
        n["position"] = [0, -780]
        continue
    c, r = POS[n["name"]]
    n["position"] = [int(c * 250), int(r * 230)]

wf = {"name": "[PROD] Redmine & AD Offboarding Automation (Linear Staff)", "nodes": nodes, "connections": conns,
      "settings": {"executionOrder": "v1", "timezone": "Europe/Kyiv", "errorWorkflow": "<ERROR_WORKFLOW_ID>",
                   "callerPolicy": "workflowsFromSameOwner", "availableInMCP": True}}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print("built", OUT, len(nodes), "nodes")
