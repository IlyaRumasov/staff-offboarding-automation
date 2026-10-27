"""Генерує tests/cases_equipment.json для флоу перевірки техніки в GLPI. Люди й техніка вигадані."""
import json
from pathlib import Path

F, H = "[Redmine] Get Open Leaver Tickets", "[Redmine] Get Ticket History"
GO, GU, GA = "[GLPI] Open Session", "[GLPI] Find User", "[GLPI] Find Assets"
PARSE, BC, ADD = "Code: Parse Tickets", "Code: Build Comment", "[Redmine] Add Comment"
T = lambda m: {"__by_ticket": {str(k): v for k, v in m.items()}}
MARK = "Перевірка техніки (GLPI):"
CLEAR_NOTE = f"{MARK} Заборгованості по техніці немає."


def admin(id_, eng="Ivan Testovenko", ukr="Тестовенко Іван"):
    return {"id": id_, "tracker": {"id": 25, "name": "Admin | Leaver"}, "subject": f"Admin Leaver - {eng}", "description": "Прошу ...",
            "custom_fields": [{"id": 11, "name": "Contractor (ENG)", "value": eng}, {"id": 103, "name": "Contractor (UKR)", "value": ukr}]}


def linear(id_, login="ivan.testovenko", fio="Тестовенко Іван Петрович", tracker=41):
    return {"id": id_, "tracker": {"id": tracker, "name": "GA | Leaver"}, "subject": f"GA | Leaver | {fio}",
            "description": f"ГА - {fio}\r\nAD - {login}\r\nТел: 0000000000", "custom_fields": []}


def fetch(*iss):
    return [{"issues": list(iss), "total_count": len(iss)}]


def hist(*notes):
    return {"issue": {"journals": [{"id": i, "notes": n} for i, n in enumerate(notes)]}}


def users(*us):
    return {"statusCode": 200, "body": {"totalcount": len(us), "data": [
        {"User.name": l, "User.realname": r, "User.firstname": f, "User.id": i + 10} for i, (l, r, f) in enumerate(us)]}}


def assets(*rows):
    return {"statusCode": 200, "body": {"totalcount": len(rows), "data": [
        {"AllAssets..name": n, "AllAssets..serial": "SN" + str(i), "AllAssets..otherserial": inv, "AllAssets..contact": c,
         "AllAssets.Manufacturer.name": "Dell Inc.", "AllAssets.State.completename": "Работает", "AllAssets.User.name": u,
         "itemtype": t, "id": str(100 + i)} for i, (t, n, u, c, inv) in enumerate(rows)]}}


ME = users(("ivan.testovenko", "Testovenko", "Ivan"))
LAPTOP = ("Computer", "Latitude 5490", "ivan.testovenko", "", "2000000000001")

cases = [
    {"name": "лінійний: ноутбук на користувачі -> коментар з переліком",
     "stubs": {F: fetch(linear(501)), GU: ME, GA: assets(LAPTOP, ("Monitor", "Dell P2419H", "ivan.testovenko", "", ""))},
     "counts": {ADD: 1},
     "has": {PARSE: [{"kind": "linear", "login": "ivan.testovenko", "names": ["Тестовенко Іван Петрович"]}],
             ADD: [{"note": f"~{MARK} за працівником числиться техніка.\nУ GLPI на користувачі ivan.testovenko:\n"
                            "– Комп'ютер «Latitude 5490», інв. № 2000000000001, сер. № SN0, Dell Inc., статус: Работает"},
                   {"note": "~– Монітор «Dell P2419H»"}]}},
    {"name": "адмін: людина є в GLPI (за ім'ям), нічого немає -> «Заборгованості по техніці немає»",
     "stubs": {F: fetch(admin(502)), GU: ME},
     "counts": {ADD: 1}, "has": {PARSE: [{"kind": "admin", "login": ""}], ADD: [{"note": CLEAR_NOTE}]}},
    {"name": "адмін: лише кирилиця в заявці -> транслітерація знаходить користувача GLPI",
     "stubs": {F: fetch(admin(503, eng="")), GU: ME},
     "has": {PARSE: [{"names": ["Тестовенко Іван"], "user_url": "~%5Etestovenko%24"}], ADD: [{"note": CLEAR_NOTE}]}},
    {"name": "адмін: людини в GLPI немає -> потрібна перевірка IT (не «немає»)",
     "stubs": {F: fetch(admin(504))},
     "has": {ADD: [{"note": f"~{MARK} потрібна перевірка IT.\nПрацівника «Ivan Testovenko» у GLPI не знайдено"}]}},
    {"name": "лінійний: людини в GLPI немає -> «Заборгованості по техніці немає»",
     "stubs": {F: fetch(linear(520))},
     "counts": {ADD: 1}, "has": {ADD: [{"note": CLEAR_NOTE}]}},
    {"name": "лінійний: є в GLPI, нічого немає -> «Заборгованості по техніці немає»",
     "stubs": {F: fetch(linear(521)), GU: ME},
     "counts": {ADD: 1}, "has": {ADD: [{"note": CLEAR_NOTE}]}},
    {"name": "лінійний: немає в GLPI, але «Контакт» з ПІБ -> перевірка IT, не «немає»",
     "stubs": {F: fetch(linear(524)), GA: assets(("Computer", "PC-17", "", "ivan.testovenko@PC-17", ""))},
     "has": {BC: [{"status": "not_in_glpi"}], ADD: [{"note": f"~{MARK} потрібна перевірка IT."}, {"note": "~PC-17"}]}},
    {"name": "лінійний: раніше числилась техніка, тепер немає -> пишемо «немає»",
     "stubs": {F: fetch(linear(522)), GU: ME, H: T({522: hist(f"{MARK} за працівником числиться техніка.\nУ GLPI ...")})},
     "counts": {ADD: 1}, "has": {ADD: [{"note": CLEAR_NOTE}]}},
    {"name": "лінійний: GLPI недоступний -> мовчимо (не скасовуємо попередній висновок)",
     "stubs": {F: fetch(linear(523)), GO: {"statusCode": 500, "body": ""}, H: T({523: hist(f"{MARK} за працівником числиться техніка.\nУ GLPI ...")})},
     "counts": {ADD: 0}, "has": {BC: [{"status": "error"}]}},
    {"name": "схожий логін у GLPI (ivan.testovenkova) -> не той користувач",
     "stubs": {F: fetch(linear(505)), GU: users(("ivan.testovenkova", "Testovenkova", "Ivanna")),
               GA: assets(("Computer", "Other", "ivan.testovenkova", "", "1"))},
     "has": {BC: [{"status": "not_in_glpi"}]}},
    {"name": "нічого не числиться, але «Контакт» з ПІБ кирилицею -> перевірка IT з переліком",
     "stubs": {F: fetch(linear(506)), GU: ME, GA: assets(("Peripheral", "Headset", "", "Тестовенко Іван", ""))},
     "has": {BC: [{"status": "check"}], ADD: [{"note": "~У полі «Контакт» GLPI згадується «ivan.testovenko»"}, {"note": "~Headset"}]}},
    {"name": "той самий висновок уже в заявці -> мовчимо",
     "stubs": {F: fetch(admin(507)), GU: ME, H: T({507: hist(CLEAR_NOTE)})},
     "counts": {ADD: 0}, "has": {BC: [{"notify": False}]}},
    {"name": "висновок змінився (раніше числилась техніка, тепер немає) -> новий коментар",
     "stubs": {F: fetch(admin(508)), GU: ME, H: T({508: hist(f"{MARK} за працівником числиться техніка.\nУ GLPI ...")})},
     "counts": {ADD: 1}, "has": {ADD: [{"note": CLEAR_NOTE}]}},
    {"name": "останнє слово про техніку за IT («закріплений ноутбук») -> мовчимо",
     "stubs": {F: fetch(admin(509)), GU: ME, H: T({509: hist("За Іваном закріплений ноутбук 2000000000001")})},
     "counts": {ADD: 0}, "has": {BC: [{"human_decided": True}]}},
    {"name": "звіт offboarding («Автоматичний offboarding ... заборгованості немає») не рахуємо як рішення людини",
     "stubs": {F: fetch(admin(510)), GU: ME, H: T({510: hist("Автоматичний offboarding: ... IT підтвердив, що заборгованості по техніці немає.")})},
     "counts": {ADD: 1}},
    {"name": "Starter і без імені/логіна пропускаємо; лінійна заявка обробляється",
     "stubs": {F: fetch(linear(511, tracker=21), linear(512, login="", fio=""), linear(513)), GU: ME},
     "counts": {PARSE: 1}, "has": {PARSE: [{"id": 513}], BC: [{"id": 513}]}},
    {"name": "адмін: GLPI недоступний -> коментар про помилку один раз",
     "steps": [
         {"stubs": {F: fetch(admin(514)), GO: {"statusCode": 400, "body": ["ERROR_WRONG_APP_TOKEN_PARAMETER", "x"]}},
          "has": {ADD: [{"note": f"~{MARK} перевірити GLPI не вдалося (вхід у GLPI 400"}]}},
         {"stubs": {F: fetch(admin(514)), GO: {"statusCode": 400, "body": ["ERROR_WRONG_APP_TOKEN_PARAMETER", "x"]},
                    H: T({514: hist(f"{MARK} перевірити GLPI не вдалося (вхід у GLPI 400: [\"ERROR_WRONG_APP_TOKEN_PARAMETER\",\"x\"]). Перевірка повториться щогодини.")})},
          "counts": {ADD: 0}}]},
    {"name": "дві заявки: різні висновки",
     "stubs": {F: fetch(linear(515), linear(516, login="petro.probnyi", fio="Пробний Петро")),
               GU: T({515: ME, 516: users()}), GA: T({515: assets(LAPTOP), 516: assets()})},
     "counts": {ADD: 2}, "has": {ADD: [{"id": 515, "note": "~числиться техніка"}, {"id": 516, "note": "~Заборгованості по техніці немає."}]}},
]

DEFAULTS = {GO: {"statusCode": 200, "body": {"session_token": "test-session"}}, GU: users(), GA: assets(), H: hist()}
for c in cases:
    for st in (c.get("steps") or [c]):
        s = st.setdefault("stubs", {})
        for k, v in DEFAULTS.items():
            if k not in s:
                s[k] = v
            elif isinstance(s[k], dict) and "__by_ticket" in s[k]:
                for it in s[F]:
                    for i in it["issues"]:
                        s[k]["__by_ticket"].setdefault(str(i["id"]), v)

Path(__file__).with_name("cases_equipment.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(cases), "cases")
