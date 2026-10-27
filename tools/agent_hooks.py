"""Спільні доробки обох флоу оффбордингу для зв'язку з Support Agent.

1. Вхід «When Called by Agent»: агент може запустити флоу для однієї заявки ({ticket_id}) одразу, не чекаючи 18:00.
   Розбір заявок сам відсіює решту (див. ONLY у parse_*.js); розклад лишається.
2. Запис у спільний аудит агента (Data Table): після оновлення заявки і після коментаря «бракує даних».
   Помилка запису в аудит флоу не зупиняє.
"""
import uuid

TRIGGER = "When Called by Agent"
LOG = "[Data Table] Log Result"
LOG_MISSING = "[Data Table] Log Missing Data"
COLS = [("ticket_id", "number"), ("kind", "string"), ("logins", "string"), ("outcome", "string"), ("dry_run", "boolean"),
        ("details", "string"), ("at", "string"), ("payload", "string")]


def _id(prefix, name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, prefix + "/" + name))


def _log_node(prefix, name, src, kind, outcome_expr):
    val = {"ticket_id": "={{ $('%s').item.json.id }}" % src, "kind": kind,
           "logins": "={{ $('%s').item.json.login || '' }}" % src, "outcome": outcome_expr,
           "dry_run": "={{ false }}", "details": "={{ String($('%s').item.json.note || '').slice(0, 300) }}" % src,
           "at": "={{ $now.toISO() }}", "payload": ""}
    return {"parameters": {"resource": "row", "operation": "insert", "dataTableId": {"__rl": True, "mode": "id", "value": "<AUDIT_TABLE>"},
                           "columns": {"mappingMode": "defineBelow", "matchingColumns": [], "value": val,
                                       "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True,
                                                   "type": t, "canBeUsedToMatch": True} for c, t in COLS]},
                           "options": {}},
            "id": _id(prefix, name), "name": name, "type": "n8n-nodes-base.dataTable", "typeVersion": 1.1, "position": [0, 0],
            "onError": "continueRegularOutput"}


def add(nodes, conns, prefix, kind, first_after_schedule, update_node, archive_if, missing_node, ready_if):
    nodes.append({"parameters": {"inputSource": "passthrough"}, "id": _id(prefix, TRIGGER), "name": TRIGGER,
                  "type": "n8n-nodes-base.executeWorkflowTrigger", "typeVersion": 1.1, "position": [0, 0]})
    conns[TRIGGER] = {"main": [[{"node": first_after_schedule, "type": "main", "index": 0}]]}
    nodes.append(_log_node(prefix, LOG, "Update Ticket Needed?", kind,
                           "={{ $('Update Ticket Needed?').item.json.close ? 'closed' : 'commented' }}"))
    nodes.append(_log_node(prefix, LOG_MISSING, ready_if, kind, "missing_data"))
    # аудит — бічна гілка після оновлення заявки (виконується першою), основний шлях до архіву не змінюється
    conns[update_node] = {"main": [[{"node": LOG, "type": "main", "index": 0}, {"node": archive_if, "type": "main", "index": 0}]]}
    conns[missing_node] = {"main": [[{"node": LOG_MISSING, "type": "main", "index": 0}]]}


def add_equipment(nodes, conns, first_after_schedule, comment_node, loop_node, build_node):
    """Флоу перевірки техніки: вхід від агента і запис у аудит після коментаря (бічна гілка, виконується першою)."""
    nodes.append({"parameters": {"inputSource": "passthrough"}, "id": _id("equipment", TRIGGER), "name": TRIGGER,
                  "type": "n8n-nodes-base.executeWorkflowTrigger", "typeVersion": 1.1, "position": [0, 0]})
    conns[TRIGGER] = {"main": [[{"node": first_after_schedule, "type": "main", "index": 0}]]}
    log = _log_node("equipment", LOG, build_node, "equipment_check", "={{ $('%s').item.json.status }}" % build_node)
    log["parameters"]["columns"]["value"]["logins"] = ""
    nodes.append(log)
    conns[comment_node] = {"main": [[{"node": LOG, "type": "main", "index": 0}, {"node": loop_node, "type": "main", "index": 0}]]}
