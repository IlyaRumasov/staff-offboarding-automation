"""Збирає workflows/admin-offboarding.json з коду в src/admin/.

Креди й ID у файлі заглушки (<..._CRED>, <ARCHIVE_SHEET_ID>), справжні підставляє deploy_admin.py з живої версії.
"""
import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "admin"
OUT = ROOT / "workflows" / "admin-offboarding.json"
REDMINE = "n8n-nodes-redmine.redmine"
nodes, conns = [], {}

C_REDMINE = {"redmineApi": {"id": "<REDMINE_CRED>", "name": "Redmine bot account"}}
C_LDAP = {"ldap": {"id": "<LDAP_CRED>", "name": "LDAP service account"}}
C_GADMIN = {"gSuiteAdminOAuth2Api": {"id": "<GADMIN_CRED>", "name": "Google Workspace Admin account"}}
C_GOAUTH = {"googleOAuth2Api": {"id": "<GOAUTH_CRED>", "name": "Google account"}}
C_ENTRA = {"microsoftEntraOAuth2Api": {"id": "<ENTRA_CRED>", "name": "Microsoft Entra ID (Azure Active Directory) account"}}
C_SHEETS = {"googleSheetsOAuth2Api": {"id": "<SHEETS_CRED>", "name": "Google Sheets account"}}


def part(file, name=None):
    text = (SRC / file).read_text(encoding="utf-8")
    if name is None:
        return text
    chunks = re.split(r"^//@@ (\w+)\n", text, flags=re.M)
    found = dict(zip(chunks[1::2], chunks[2::2]))
    body = found[name]
    return re.sub(r"\n// ===== .*$", "", body.rstrip(), flags=re.S).rstrip() + "\n"


def node(name, type_, params, x, y, version=1, **extra):
    n = {"parameters": params, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "admin/" + name)), "name": name,
         "type": type_, "typeVersion": version, "position": [x, y]}
    n.update(extra)
    nodes.append(n)
    return name


def link(src, dst, out=0):
    m = conns.setdefault(src, {"main": []})["main"]
    while len(m) <= out:
        m.append([])
    m[out].append({"node": dst, "type": "main", "index": 0})


def code(name, file, part_name, x, y, replace=None):
    js = part(file, part_name)
    for k, v in (replace or {}).items():
        js = js.replace(k, v)
    return node(name, "n8n-nodes-base.code", {"jsCode": js}, x, y, version=2)


def if_true(name, left, x, y):
    return node(name, "n8n-nodes-base.if", {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                       "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)), "leftValue": left, "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                       "combinator": "and"},
        "looseTypeValidation": True, "options": {}}, x, y, version=2.2)


def http(name, method, url, cred_type, creds, x, y, body=None):
    p = {"method": method, "url": url, "authentication": "predefinedCredentialType", "nodeCredentialType": cred_type,
         "options": {"response": {"response": {"fullResponse": True, "neverError": True}}}}
    if body is not None:
        p.update(sendBody=True, specifyBody="json", jsonBody=body)
    return node(name, "n8n-nodes-base.httpRequest", p, x, y, version=4.2, onError="continueRegularOutput", credentials=creds)


STICKY = """## 🛡️ [PROD] Offboarding адмін-персоналу (Admin | Leaver)
AD, Google Workspace (призупинення + передача диска), Microsoft 365, звіт у Redmine, архів у Google Sheets.

**Розклад:** щодня о 18:00 (Europe/Kyiv).

**Пошук людини** в кожній системі за ім'ям і прізвищем (поле Contractor (ENG), інакше UKR латиницею за КМУ-2010), в обох порядках. Логін не вгадується. Дія лише при **єдиному** збігу; кілька або жодного: коментар, нічого не змінюємо.
* AD: блокування (ACCOUNTDISABLE, інші прапорці не чіпаємо) і перенос в «Уволенные», лише для OU=AllUsers.
* Google: Suspended. Диск: на e-mail із заявки одразу; якщо вказано лише ім'я (або нічого, тоді менеджер із поля Manager), флоу пропонує людину в коментарі й передає після відповіді «так».
* M365: видалення лише члена тенанта (не гостей #EXT#).

**Закриття заявки** (статус 17) лише коли: немає проблем, диск вирішено, і в заявці є коментар IT «Заборгованості по техніці немає». «Закріплений ноутбук» або немає підтвердження: доступи закриваємо, заявка відкрита.
**Без дати звільнення** нічого не робимо, пишемо коментар. Повторний запуск після закриття доступів: лише короткий коментар. Той самий коментар двічі не пишемо (static data).
**Помилки:** Error Workflow."""

Y = 400
X = 220  # крок по горизонталі


def at(i):
    return i * X


node("Every Day 18:00", "n8n-nodes-base.scheduleTrigger",
     {"rule": {"interval": [{"field": "cronExpression", "expression": "0 18 * * *"}]}}, at(0), Y, version=1.2)
node("[Redmine] Get Open Leaver Tickets", REDMINE, {"operation": "getAll", "returnAll": True,
     "filters": {"project_id": "staff-leavers", "tracker_id": "25", "status_id": "open"}, "options": {}}, at(1), Y, credentials=C_REDMINE)
code("Code: Parse Tickets", "parse_admin.js", None, at(2), Y)
if_true("Ticket Ready?", "={{ $json.action === 'process' }}", at(3), Y)
node("[Redmine] Comment Missing Data", REDMINE, {"operation": "update", "issueId": "={{ $json.id }}", "notes": "={{ $json.note }}",
     "additionalFields": {}, "options": {}}, at(4), Y + 260, credentials=C_REDMINE)
node("Loop Over Tickets", "n8n-nodes-base.splitInBatches", {"options": {}}, at(4), Y - 100, version=3)
node("[Redmine] Get Ticket History", REDMINE, {"operation": "get", "issueId": "={{ $json.id }}", "include": ["journals"], "options": {}},
     at(5), Y - 100, credentials=C_REDMINE)
node("[AD] Search User", "n8n-nodes-base.ldap", {"baseDN": "DC=example,DC=com", "searchFor": "custom",
     "customFilter": "={{ $('Loop Over Tickets').first().json.ldap_filter }}", "returnAll": True,
     "options": {"scope": "sub", "attributes": ["userAccountControl", "sAMAccountName", "givenName", "sn", "displayName", "mail", "userPrincipalName"]}},
     at(6), Y - 100, alwaysOutputData=True, credentials=C_LDAP)
code("Code: Decide AD Action", "decide_ad.js", None, at(7), Y - 100)
if_true("Disable in AD?", "={{ $json.ad.status === 'disable' }}", at(8), Y - 100)
node("[AD] Disable Account", "n8n-nodes-base.ldap", {"operation": "update", "dn": "={{ $json.ad.dn }}",
     "attributes": {"replace": [{"id": "userAccountControl", "value": "={{ $json.ad.new_uac }}"}]}},
     at(9), Y - 300, onError="continueRegularOutput", credentials=C_LDAP)
if_true("Disabled OK?", "={{ !$json.error }}", at(10), Y - 300)
node("[AD] Move to Fired OU", "n8n-nodes-base.ldap", {"operation": "rename",
     "dn": "={{ $('Code: Decide AD Action').first().json.ad.dn }}", "targetDn": "={{ $('Code: Decide AD Action').first().json.ad.target_dn }}"},
     at(11), Y - 400, onError="continueRegularOutput", credentials=C_LDAP)
code("Code: Prepare Google Search", "prepare_google_search.js", None, at(12), Y - 100)
http("[Google] Find User", "GET", "={{ $json.url }}", "gSuiteAdminOAuth2Api", C_GADMIN, at(13), Y - 100)
code("Code: Decide Google Action", "decide_google.js", None, at(14), Y - 100)
if_true("Suspend in Google?", "={{ $json.google.status === 'suspend' }}", at(15), Y - 100)
http("[Google] Suspend User", "PUT", "=https://admin.googleapis.com/admin/directory/v1/users/{{ $json.google.id }}",
     "gSuiteAdminOAuth2Api", C_GADMIN, at(16), Y - 300, body='{"suspended": true}')
code("Code: Prepare Drive Transfer", "prepare_drive_transfer.js", None, at(17), Y - 100)
if_true("Recipient Lookup Needed?", "={{ $json.url !== '' }}", at(18), Y - 100)
http("[Google] Find Drive Recipient", "GET", "={{ $json.url }}", "gSuiteAdminOAuth2Api", C_GADMIN, at(19), Y - 300)
code("Code: Decide Drive Action", "decide_drive.js", None, at(20), Y - 100)
if_true("Transfer Drive?", "={{ $json.drive.action === 'transfer' }}", at(21), Y - 100)
http("[Google] Transfer Drive", "POST", "https://admin.googleapis.com/admin/datatransfer/v1/transfers", "googleOAuth2Api", C_GOAUTH,
     at(22), Y - 300, body='={\n  "oldOwnerUserId": "{{ $json.google.id }}",\n  "newOwnerUserId": "{{ $json.drive.recipient_id }}",\n'
     '  "applicationDataTransfers": [{"applicationId": "55656082996",\n    "applicationTransferParams": [{"key": "PRIVACY_LEVEL", "value": ["SHARED", "PRIVATE"]}]}]\n}')
code("Code: Prepare M365 Search", "prepare_m365_search.js", None, at(23), Y - 100)
http("[M365] Search User", "GET", "={{ $json.url }}", "microsoftEntraOAuth2Api", C_ENTRA, at(24), Y - 100)
code("Code: Decide M365 Action", "decide_m365.js", None, at(25), Y - 100)
if_true("Delete in M365?", "={{ $json.m365.status === 'delete' }}", at(26), Y - 100)
http("[M365] Delete User", "DELETE", "=https://graph.microsoft.com/v1.0/users/{{ $json.m365.id }}", "microsoftEntraOAuth2Api", C_ENTRA,
     at(27), Y - 300)
code("Code: Build Report", "build_report.js", None, at(28), Y - 100)
if_true("Update Ticket Needed?", "={{ $json.notify }}", at(29), Y - 100)
node("[Redmine] Update Ticket", REDMINE, {"operation": "update", "issueId": "={{ $json.id }}", "notes": "={{ $json.note }}",
     "additionalFields": {"status_id": "={{ $json.close ? '17' : undefined }}"}, "options": {}}, at(30), Y - 200, credentials=C_REDMINE)
if_true("Add to Archive?", "={{ $('Code: Build Report').item.json.archive }}", at(31), Y - 200)
node("[Sheets] Add to Archive", "n8n-nodes-base.googleSheets", {
    "operation": "append", "documentId": {"__rl": True, "value": "<ARCHIVE_SHEET_ID>", "mode": "id"},
    "sheetName": {"__rl": True, "value": "gid=0", "mode": "list"},
    "columns": {"mappingMode": "defineBelow", "value": {
        "Date": "={{ $('Code: Build Report').item.json.leaver_date }}",
        "Login": "={{ $('Code: Build Report').item.json.login }}",
        "Ticket ID": "={{ $('Code: Build Report').item.json.id }}"},
        "matchingColumns": [], "schema": [
            {"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True, "type": "string",
             "canBeUsedToMatch": True, "removed": False} for c in ("Date", "Login", "Ticket ID", "Google guest account ")],
        "attemptToConvertTypes": False, "convertFieldsToString": False},
    "options": {}}, at(32), Y - 300, version=4, retryOnFail=True, credentials=C_SHEETS)
node("Sticky Note: Overview", "n8n-nodes-base.stickyNote", {"content": STICKY, "height": 700, "width": 700, "color": 6}, 0, -500)

link("Every Day 18:00", "[Redmine] Get Open Leaver Tickets")
link("[Redmine] Get Open Leaver Tickets", "Code: Parse Tickets")
link("Code: Parse Tickets", "Ticket Ready?")
link("Ticket Ready?", "Loop Over Tickets", 0)
link("Ticket Ready?", "[Redmine] Comment Missing Data", 1)
link("Loop Over Tickets", "[Redmine] Get Ticket History", 1)
link("[Redmine] Get Ticket History", "[AD] Search User")
link("[AD] Search User", "Code: Decide AD Action")
link("Code: Decide AD Action", "Disable in AD?")
link("Disable in AD?", "[AD] Disable Account", 0)
link("Disable in AD?", "Code: Prepare Google Search", 1)
link("[AD] Disable Account", "Disabled OK?")
link("Disabled OK?", "[AD] Move to Fired OU", 0)
link("Disabled OK?", "Code: Prepare Google Search", 1)
link("[AD] Move to Fired OU", "Code: Prepare Google Search")
link("Code: Prepare Google Search", "[Google] Find User")
link("[Google] Find User", "Code: Decide Google Action")
link("Code: Decide Google Action", "Suspend in Google?")
link("Suspend in Google?", "[Google] Suspend User", 0)
link("Suspend in Google?", "Code: Prepare Drive Transfer", 1)
link("[Google] Suspend User", "Code: Prepare Drive Transfer")
link("Code: Prepare Drive Transfer", "Recipient Lookup Needed?")
link("Recipient Lookup Needed?", "[Google] Find Drive Recipient", 0)
link("Recipient Lookup Needed?", "Code: Decide Drive Action", 1)
link("[Google] Find Drive Recipient", "Code: Decide Drive Action")
link("Code: Decide Drive Action", "Transfer Drive?")
link("Transfer Drive?", "[Google] Transfer Drive", 0)
link("Transfer Drive?", "Code: Prepare M365 Search", 1)
link("[Google] Transfer Drive", "Code: Prepare M365 Search")
link("Code: Prepare M365 Search", "[M365] Search User")
link("[M365] Search User", "Code: Decide M365 Action")
link("Code: Decide M365 Action", "Delete in M365?")
link("Delete in M365?", "[M365] Delete User", 0)
link("Delete in M365?", "Code: Build Report", 1)
link("[M365] Delete User", "Code: Build Report")
link("Code: Build Report", "Update Ticket Needed?")
link("Update Ticket Needed?", "[Redmine] Update Ticket", 0)
link("Update Ticket Needed?", "Loop Over Tickets", 1)
link("[Redmine] Update Ticket", "Add to Archive?")
link("Add to Archive?", "[Sheets] Add to Archive", 0)
link("Add to Archive?", "Loop Over Tickets", 1)
link("[Sheets] Add to Archive", "Loop Over Tickets")


# Розкладка сіткою по етапах: розбір заявок, AD, Google, Диск, M365 і звіт. Лише позиції нод.
LAYOUT_ROWS = [
    ["Every Day 18:00", "[Redmine] Get Open Leaver Tickets", "Code: Parse Tickets", "Ticket Ready?", "Loop Over Tickets",
     "[Redmine] Get Ticket History", "[AD] Search User", "Code: Decide AD Action"],
    ["Disable in AD?", "[AD] Disable Account", "Disabled OK?", "[AD] Move to Fired OU", "Code: Prepare Google Search",
     "[Google] Find User", "Code: Decide Google Action", "Suspend in Google?"],
    ["[Google] Suspend User", "Code: Prepare Drive Transfer", "Recipient Lookup Needed?", "[Google] Find Drive Recipient",
     "Code: Decide Drive Action", "Transfer Drive?", "[Google] Transfer Drive", "Code: Prepare M365 Search"],
    ["[M365] Search User", "Code: Decide M365 Action", "Delete in M365?", "[M365] Delete User", "Code: Build Report",
     "Update Ticket Needed?", "[Redmine] Update Ticket", "Add to Archive?"],
]
LAYOUT_EXTRA = {"[Redmine] Comment Missing Data": (3, 0.75), "[Sheets] Add to Archive": (7, 4)}

POS = {nm: (c, r) for r, row in enumerate(LAYOUT_ROWS) for c, nm in enumerate(row)}
POS.update(LAYOUT_EXTRA)
for n in nodes:
    if n["type"] == "n8n-nodes-base.stickyNote":
        n["position"] = [0, -780]
        continue
    c, r = POS[n["name"]]
    n["position"] = [int(c * 250), int(r * 230)]

wf = {"name": "[PROD] Redmine & AD Offboarding Automation (Admin Staff) / [PROD] Автоматизація звільнення (Адмін персонал)",
      "nodes": nodes, "connections": conns,
      "settings": {"executionOrder": "v1", "timezone": "Europe/Kyiv", "errorWorkflow": "<ERROR_WORKFLOW_ID>",
                   "callerPolicy": "workflowsFromSameOwner", "availableInMCP": True}}
OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print("built", OUT, len(nodes), "nodes")
