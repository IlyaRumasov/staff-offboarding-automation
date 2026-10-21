"""Генерує tests/cases_admin.json для флоу offboarding адмін-персоналу. Люди вигадані, формати як у бойових заявках."""
import json
from pathlib import Path

OU = "OU=administrative_staff,OU=AllUsers,OU=COMPANY,DC=example,DC=com"
FIRED = "OU=Уволенные,DC=example,DC=com"
F, H, LS = "[Redmine] Get Open Leaver Tickets", "[Redmine] Get Ticket History", "[AD] Search User"
UP, MV = "[AD] Disable Account", "[AD] Move to Fired OU"
GS, SU, GR, TR = "[Google] Find User", "[Google] Suspend User", "[Google] Find Drive Recipient", "[Google] Transfer Drive"
MS, MD = "[M365] Search User", "[M365] Delete User"
PARSE, ST, FR = "Code: Parse Tickets", "Code: Prepare Drive Transfer", "Code: Build Report"
UPD, CMISS, SHEET = "[Redmine] Update Ticket", "[Redmine] Comment Missing Data", "[Sheets] Add to Archive"
BOT_OLD = ("Автоматичний Offboarding успішно завершено!\n\nДетальний звіт про закриття доступів:\n1. Active Directory: ...\n"
           "3. Google Диск (Перенесення документів):\n   • Новий власник (керівник): x@corp.example.com\n   • Статус: Успішно ініційовано системою.\n"
           "Заборгованості по техніці немає.")
EQ_OK = "Заборгованості по техніці немає"
EQ_DEBT = "Добрий день. За Іваном закріплений ноутбук 2000000000001"


def issue(id_, eng="Ivan Testovenko", ukr="Тестовенко Іван", date="$YESTERDAY", manager="Mariia Probna", desc=None):
    d = desc if desc is not None else (f"Доброго дня!\r\nПрошу запустити процес припинення співпраці з {eng}/Trainer/Lutsk\r\n"
                                       "Переадресація пошти: видалити\r\nПереадресація диску: recv.person@corp.example.com\r\n\r\nДякую.")
    cfs = [{"id": 11, "name": "Contractor (ENG)", "value": eng}, {"id": 103, "name": "Contractor (UKR)", "value": ukr},
           {"id": 25, "name": "Manager", "value": manager}]
    if date:
        cfs.append({"id": 30, "name": "Termination date", "value": date})
    return {"id": id_, "tracker": {"id": 25, "name": "Admin | Leaver"}, "status": {"id": 1, "name": "New"},
            "subject": f"Admin Leaver - {eng}", "description": d, "custom_fields": cfs}


def hist(*notes, status=1):
    return {"issue": {"status": {"id": status}, "journals": [{"id": i, "notes": n, "user": {"name": "Automation Bot" if "Автоматичний" in n else "IT"}}
                                                             for i, n in enumerate(notes)]}}


def aduser(sam, gn, sn, ou=OU, uac="512"):
    return {"dn": f"CN={gn} {sn},{ou}", "sAMAccountName": sam, "givenName": gn, "sn": sn, "userAccountControl": uac}


def guser(email, full, suspended=False, id_=None):
    return {"id": id_ or "g-" + email.split("@")[0], "primaryEmail": email, "name": {"fullName": full}, "suspended": suspended}


def gsearch(*users):
    return {"statusCode": 200, "body": {"users": list(users)} if users else {"kind": "admin#directory#users"}}


def msearch(*upns):
    return {"statusCode": 200, "body": {"value": [{"id": "m-" + u.split("@")[0], "userPrincipalName": u, "userType": "Guest" if "#EXT#" in u else "Member"} for u in upns]}}


T = lambda m: {"__by_ticket": {str(k): v for k, v in m.items()}}
LEAVER = guser("ivan.testovenko@corp.example.com", "Ivan Testovenko")
RECV = guser("recv.person@corp.example.com", "Recv Person")


def std(id_, **over):
    """Типовий набір заглушок: людина є в AD, Google і M365, отримувач диска є, IT підтвердив техніку."""
    s = {H: T({id_: hist(EQ_OK)}), LS: T({id_: [aduser("ivan.testovenko", "Ivan", "Testovenko")]}),
         GS: T({id_: gsearch(LEAVER)}), GR: T({id_: {"statusCode": 200, "body": RECV}}),
         MS: T({id_: msearch("ivan.testovenko@m365.example.com")})}
    s.update(over)
    return s


def fetch(*iss):
    return [{"issues": list(iss), "total_count": len(iss)}]


cases = [
    {"name": "щасливий шлях: AD, Google, диск на e-mail, M365, техніка ок -> закрито",
     "stubs": {F: fetch(issue(301)), **std(301)},
     "counts": {UP: 1, MV: 1, SU: 1, TR: 1, MD: 1, UPD: 1, SHEET: 1, CMISS: 0},
     "has": {FR: [{"close": True, "note": "~доступи закрито, заявку закрито"}, {"note": "~Акаунт ivan.testovenko заблоковано"},
                  {"note": "~Диск: перенесення запущено (кому: Recv Person, recv.person@corp.example.com)"},
                  {"note": "~Акаунт ivan.testovenko@m365.example.com видалено"}, {"note": "~IT підтвердив"}],
             "Code: Decide AD Action": [{"ad": {"status": "disable", "dn": f"CN=Ivan Testovenko,{OU}", "target_dn": f"CN=Ivan Testovenko,{FIRED}",
                                           "new_uac": "514", "login": "ivan.testovenko", "candidates": "ivan.testovenko (administrative_staff, активний)", "by_login_pattern": False, "ignored_disabled": ""}}]}},
    {"name": "за працівником ноутбук: доступи закриваємо, заявка відкрита",
     "stubs": {F: fetch(issue(302)), **std(302, **{H: T({302: hist(EQ_DEBT)})})},
     "counts": {UP: 1, SU: 1, TR: 1, MD: 1, UPD: 1, SHEET: 0},
     "has": {FR: [{"close": False, "note": "~числиться техніка"}, {"note": "~заявку залишено відкритою"}]}},
    {"name": "немає підтвердження IT щодо техніки: відкрита",
     "stubs": {F: fetch(issue(303)), **std(303, **{H: T({303: hist()})})},
     "has": {FR: [{"close": False, "note": "~Підтвердження IT щодо техніки ще немає"}]}},
    {"name": "старий бот писав «Заборгованості немає» у своєму звіті: не рахуємо",
     "stubs": {F: fetch(issue(304)), **std(304, **{H: T({304: hist(BOT_OLD)})})},
     "has": {ST: [{"equipment": "unknown", "prior_report": True}]}},
    {"name": "ноутбук, потім IT: «Заборгованості немає» -> останній коментар вирішує",
     "stubs": {F: fetch(issue(305)), **std(305, **{H: T({305: hist(EQ_DEBT, "Техніку повернуто. " + EQ_OK)})})},
     "has": {ST: [{"equipment": "ok"}], FR: [{"close": True}]}},
    {"name": "ім'я англ. у порядку «Прізвище Ім'я»: шукаємо обидва порядки",
     "stubs": {F: fetch(issue(306, eng="Probenko Olha", ukr="Пробенко Ольга ")), **std(306)},
     "counts": {"Code: Prepare Google Search": 2},
     "has": {PARSE: [{"pairs": [["Probenko", "Olha"], ["Olha", "Probenko"]],
                      "ldap_filter": "(&(objectClass=user)(|(&(givenName=Probenko)(sn=Olha))(&(givenName=Olha)(sn=Probenko))(sAMAccountName=probenko.olha)(sAMAccountName=p.olha)(sAMAccountName=ms.p.olha)(sAMAccountName=ms.probenko.olha)(sAMAccountName=olha.probenko)(sAMAccountName=o.probenko)(sAMAccountName=ms.o.probenko)(sAMAccountName=ms.olha.probenko)))"}]}},
    {"name": "англ. ім'я порожнє: беремо укр. латиницею",
     "stubs": {F: fetch(issue(307, eng="", ukr="Зразковий Олег")), **std(307)},
     "has": {PARSE: [{"pairs": [["Zrazkovyi", "Oleh"], ["Oleh", "Zrazkovyi"]]}]}},
    {"name": "немає дати звільнення: коментар, нічого не робимо (старий флоу брав «сьогодні»)",
     "stubs": {F: fetch(issue(308, date=None))},
     "counts": {CMISS: 1, LS: 0}, "has": {CMISS: [{"id": 308, "note": "~не вказано дату звільнення"}]}},
    {"name": "дата завтра: нічого", "stubs": {F: fetch(issue(309, date="$TOMORROW"))}, "counts": {CMISS: 0, LS: 0}},
    {"name": "диск: лише ім'я -> пропонуємо людину, не передаємо",
     "stubs": {F: fetch(issue(310, desc="Доброго дня!\r\nПрошу запустити процес припинення співпраці з Ivan Testovenko\r\nДані пошти та диску передати - Тестова Жанна\r\n\r\nДякую.")),
               **std(310, **{GR: T({310: gsearch(guser("zhanna.testova@corp.example.com", "Zhanna Testova"))})})},
     "counts": {TR: 0, "Code: Prepare Drive Transfer": 2},
     "has": {FR: [{"close": False, "note": "~Передати диск: Zhanna Testova (zhanna.testova@corp.example.com)?"}]}},
    {"name": "диск: на питання відповіли «так» -> передаємо і закриваємо",
     "stubs": {F: fetch(issue(311, desc="Доброго дня!\r\nДані пошти та диску передати - Тестова Жанна\r\n")),
               **std(311, **{H: T({311: hist("⚠ Автоматичний offboarding ... \n• Передати диск: Zhanna Testova (zhanna.testova@corp.example.com)?\n", "так", EQ_OK)}),
                             GR: T({311: {"statusCode": 200, "body": guser("zhanna.testova@corp.example.com", "Zhanna Testova")}})})},
     "counts": {TR: 1, "Code: Prepare Drive Transfer": 1},
     "has": {ST: [{"confirmed_email": "zhanna.testova@corp.example.com"}], FR: [{"close": True, "note": "~кому: Zhanna Testova"}]}},
    {"name": "диск: «не потрібно» -> без пошуку отримувача",
     "stubs": {F: fetch(issue(312, desc="Переадресація пошти: не потрібно\r\nПереадресація диску: не потрібно\r\n")), **std(312)},
     "counts": {GR: 0, TR: 0}, "has": {FR: [{"close": True, "note": "~передавати не потрібно"}]}},
    {"name": "диск: нічого не сказано -> пропонуємо менеджера з поля Manager",
     "stubs": {F: fetch(issue(313, desc="Прошу запустити процес припинення співпраці з Ivan Testovenko\r\n", manager="Mariia Probna")),
               **std(313, **{GR: T({313: gsearch(guser("mariia.probna@corp.example.com", "Mariia Probna"))})})},
     "has": {PARSE: [{"drive": {"mode": "manager", "name": "Mariia Probna", "pairs": [["Mariia", "Probna"], ["Probna", "Mariia"]],
                                "text": "не вказано, менеджер: Mariia Probna"}}],
             FR: [{"note": "~Передати диск: Mariia Probna (mariia.probna@corp.example.com)?"}]}},
    {"name": "диск: нічого не сказано і менеджера немає -> просимо e-mail",
     "stubs": {F: fetch(issue(314, desc="Прошу запустити процес.\r\n", manager="-")), **std(314)},
     "counts": {GR: 0}, "has": {FR: [{"close": False, "note": "~не зрозуміло, кому передати"}]}},
    {"name": "AD: два акаунти -> не блокуємо, решта систем працює",
     "stubs": {F: fetch(issue(315)), **std(315, **{LS: T({315: [aduser("ivan.testovenko", "Ivan", "Testovenko"), aduser("i.testovenko", "Ivan", "Testovenko")]})})},
     "counts": {UP: 0, SU: 1, MD: 1},
     "has": {FR: [{"close": False, "note": "~Знайдено кілька акаунтів: ivan.testovenko (administrative_staff, активний); i.testovenko"}]}},
    {"name": "AD: ім'я/прізвище порожні, знайдено за шаблоном ms.і.прізвище",
     "stubs": {F: fetch(issue(328)), **std(328, **{LS: T({328: [{"dn": f"CN=ms.i.testovenko,{OU}", "sAMAccountName": "ms.i.testovenko", "givenName": [], "sn": [], "userAccountControl": "512"}]})})},
     "counts": {UP: 1}, "has": {FR: [{"note": "~ms.i.testovenko заблоковано та переміщено в OU «Уволенные». (ім’я/прізвище в AD не заповнені, знайдено за шаблоном логіна)"}]}},
    {"name": "AD: є і збіг за ім'ям, і інший за шаблоном логіна -> беремо збіг за ім'ям",
     "stubs": {F: fetch(issue(329)), **std(329, **{LS: T({329: [aduser("ivan.testovenko", "Ivan", "Testovenko"),
               {"dn": f"CN=old,{OU}", "sAMAccountName": "i.testovenko", "givenName": [], "sn": [], "userAccountControl": "512"}]})})},
     "counts": {UP: 1}, "has": {"Code: Decide AD Action": [{"ad": {"status": "disable", "dn": f"CN=Ivan Testovenko,{OU}", "target_dn": f"CN=Ivan Testovenko,{FIRED}",
               "new_uac": "514", "login": "ivan.testovenko", "candidates": "ivan.testovenko (administrative_staff, активний)", "by_login_pattern": False, "ignored_disabled": ""}}]}},
    {"name": "AD: активний + заблокований дублікат -> блокуємо активного, дублікат у звіті",
     "stubs": {F: fetch(issue(330)), **std(330, **{LS: T({330: [aduser("ivan.testovenko", "Ivan", "Testovenko"),
               aduser("i.testovenko", "Ivan", "Testovenko", ou="OU=Client,OU=AllUsers,OU=COMPANY,DC=example,DC=com", uac="514")]})})},
     "counts": {UP: 1}, "has": {FR: [{"note": "~інші акаунти з таким іменем уже заблоковані й пропущені: i.testovenko (Client, заблокований)"}]}},
    {"name": "AD: два активні -> стоп (не блокуємо)",
     "stubs": {F: fetch(issue(331)), **std(331, **{LS: T({331: [aduser("ivan.testovenko", "Ivan", "Testovenko"), aduser("i.testovenko", "Ivan", "Testovenko")]})})},
     "counts": {UP: 0}, "has": {FR: [{"note": "~Знайдено кілька акаунтів"}]}},
    {"name": "ім'я англ. з трьох слів («Adam Leopold Tester»): шукаємо «перше + останнє» в AD, Google, M365",
     "stubs": {F: fetch(issue(332, eng="Adam Leopold Tester", ukr="Адам Леопольд Тестер")), **std(332, **{
               LS: T({332: [aduser("adam.tester", "Adam", "Tester")]}),
               GS: T({332: gsearch(guser("adam.tester@corp.example.com", "Adam Tester"))}),
               MS: T({332: msearch("adam.tester@m365.example.com")})})},
     "counts": {UP: 1, SU: 1, MD: 1, "Code: Prepare Google Search": 4},
     "has": {PARSE: [{"pairs": [["Adam", "Tester"], ["Tester", "Adam"], ["Adam", "Leopold"], ["Leopold", "Adam"]]}], FR: [{"close": True}]}},
    {"name": "AD: не знайдено (уже видалено) -> не проблема, закриваємо",
     "stubs": {F: fetch(issue(316)), **std(316, **{LS: T({316: []})})},
     "counts": {UP: 0}, "has": {FR: [{"close": True, "note": "~не знайдено (можливо, вже видалено)"}]}},
    {"name": "Google: не знайдено -> проблема, диск не виконувався",
     "stubs": {F: fetch(issue(317)), **std(317, **{GS: T({317: gsearch()})})},
     "counts": {SU: 0, TR: 0},
     "has": {FR: [{"close": False, "note": "~Google Workspace: Акаунт за ім'ям «Ivan Testovenko» не знайдено"}, {"note": "~акаунт Google працівника не знайдено"}]}},
    {"name": "повторний запуск: усе вже закрито, техніка ок -> короткий коментар і закриття",
     "stubs": {F: fetch(issue(318)), **std(318, **{H: T({318: hist(BOT_OLD, EQ_OK)}),
               LS: T({318: [aduser("ivan.testovenko", "Ivan", "Testovenko", ou=FIRED, uac="514")]}),
               GS: T({318: gsearch(guser("ivan.testovenko@corp.example.com", "Ivan Testovenko", suspended=True))}),
               MS: T({318: msearch()})})},
     "counts": {UP: 0, SU: 0, MD: 0, UPD: 1, SHEET: 0},
     "has": {FR: [{"close": True, "note": "~доступи закрито раніше (див. попередній звіт). IT підтвердив"}]}},
    {"name": "повторний запуск з ноутбуком: короткий коментар один раз, наступного дня мовчимо",
     "steps": [
         {"stubs": {F: fetch(issue(319)), **std(319, **{H: T({319: hist(BOT_OLD, EQ_DEBT)}),
                    LS: T({319: [aduser("ivan.testovenko", "Ivan", "Testovenko", ou=FIRED, uac="514")]}),
                    GS: T({319: gsearch(guser("ivan.testovenko@corp.example.com", "Ivan Testovenko", suspended=True))}), MS: T({319: msearch()})})},
          "counts": {UPD: 1}, "has": {FR: [{"close": False, "note": "~повторно нічого не виконувалось"}]}},
         {"stubs": {F: fetch(issue(319)), **std(319, **{H: T({319: hist(BOT_OLD, EQ_DEBT)}),
                    LS: T({319: [aduser("ivan.testovenko", "Ivan", "Testovenko", ou=FIRED, uac="514")]}),
                    GS: T({319: gsearch(guser("ivan.testovenko@corp.example.com", "Ivan Testovenko", suspended=True))}), MS: T({319: msearch()})})},
          "counts": {UPD: 0}}]},
    {"name": "помилка блокування в AD: перенос не робимо, решта систем працює",
     "stubs": {F: fetch(issue(320)), **std(320, **{UP: T({320: {"__throw": "Insufficient access rights"}})})},
     "counts": {MV: 0, SU: 1},
     "has": {FR: [{"close": False, "note": "~НЕ виконано (блокування: "}, {"note": "~Insufficient access rights"}]}},
    {"name": "помилка переносу в AD",
     "stubs": {F: fetch(issue(321)), **std(321, **{MV: T({321: {"__throw": "No such object"}})})},
     "has": {FR: [{"close": False, "note": "~перенесення в «Уволенные»: No such object"}]}},
    {"name": "M365: гостя #EXT# не рахуємо, видаляємо лише члена тенанта",
     "stubs": {F: fetch(issue(322)), **std(322, **{MS: T({322: msearch("ivan.testovenko@m365.example.com", "ivan.testovenko_example.com#EXT#@x.onmicrosoft.com")})})},
     "counts": {MD: 1}, "has": {FR: [{"close": True}]}},
    {"name": "M365: два члени тенанта -> нічого не видаляємо",
     "stubs": {F: fetch(issue(323)), **std(323, **{MS: T({323: msearch("ivan.testovenko@m365.example.com", "ivan.testovenko2@m365.example.com")})})},
     "counts": {MD: 0}, "has": {FR: [{"close": False, "note": "~Microsoft 365: Знайдено кілька акаунтів"}]}},
    {"name": "логіни в системах різні: попередження",
     "stubs": {F: fetch(issue(324)), **std(324, **{LS: T({324: [aduser("i.testovenko", "Ivan", "Testovenko")]})})},
     "has": {FR: [{"note": "~Логіни в системах відрізняються (i.testovenko, ivan.testovenko)"}]}},
    {"name": "передача диска 403: проблема, заявка відкрита",
     "stubs": {F: fetch(issue(325)), **std(325, **{TR: T({325: {"statusCode": 403, "body": {"error": {"message": "Insufficient Permission"}}}})})},
     "has": {FR: [{"close": False, "note": "~перенесення НЕ запущено (403: Insufficient Permission)"}]}},
    {"name": "дві заявки: проблема в першій не зупиняє другу",
     "stubs": {F: fetch(issue(326), issue(327)), **std(326),
               H: T({326: hist(EQ_OK), 327: hist(EQ_OK)}),
               LS: T({326: [aduser("ivan.testovenko", "Ivan", "Testovenko")], 327: []}),
               GS: T({326: gsearch(), 327: gsearch(LEAVER)}),
               GR: T({327: {"statusCode": 200, "body": RECV}}),
               MS: T({326: msearch(), 327: msearch()})},
     "counts": {UPD: 2, SHEET: 1}, "has": {UPD: [{"id": 326}, {"id": 327}]}},
]

DEFAULTS = {SU: {"statusCode": 200, "body": {"suspended": True}}, TR: {"statusCode": 200, "body": {"overallTransferStatusCode": "inProgress"}},
            MD: {"statusCode": 204, "body": ""}, MS: {"statusCode": 200, "body": {"value": []}}, GS: gsearch(), H: hist()}
for c in cases:
    for st in (c.get("steps") or [c]):
        s = st.setdefault("stubs", {})
        for k, v in DEFAULTS.items():
            if k not in s:
                s[k] = v
            elif isinstance(s[k], dict) and "__by_ticket" in s[k]:
                pass
        # заглушки «за заявкою» без запису для конкретної заявки повертали б ехо; підставляємо типове значення
        for k, v in DEFAULTS.items():
            if isinstance(s.get(k), dict) and "__by_ticket" in s[k]:
                ids = [str(i["id"]) for it in s[F] for i in it.get("issues", [it])]
                for i in ids:
                    s[k]["__by_ticket"].setdefault(i, v)

Path(__file__).with_name("cases_admin.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(cases), "cases")
