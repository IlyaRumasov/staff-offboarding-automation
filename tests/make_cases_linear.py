"""Генерує tests/cases_linear.json. Заявки вигадані, структура як у справжніх (опис з рядками «ПІБ - », «AD - », «Тел: »)."""
import json
from pathlib import Path

OU = "OU=AllUsers,OU=COMPANY,DC=example,DC=com"
FIRED = "OU=Уволенные,DC=example,DC=com"
F, LS, DEC = "[Redmine] Get Open Leaver Tickets", "[AD] Search User", "Code: Decide AD Action"
UP, MV, GW, GC = "[AD] Disable Account", "[AD] Move to Fired OU", "[Google] Delete Guest", "[Google] Check Guest Exists"
UPDATE = "[Redmine] Update Ticket"
CLOSE, SHEET, CMISS, CPROB = UPDATE + "::close=True", "[Sheets] Add to Archive", "[Redmine] Comment Missing Data", UPDATE + "::close=False"


def issue(id_, login="test.user", date="$YESTERDAY", tracker=41, cf=None, desc=None, subject_date=None, fio="Тестовий Користувач Іванович", tenure=None):
    d = desc if desc is not None else (
        "В системі HRIS створено запит на розірвання договору. \r\n"
        f"        ГА - {fio} \r\n        AD - {login} \r\n        тел: +380000000{id_ % 1000:03d} \r\n"
        "        Автор запиту - t.author\r\n        Заборгованості по техніці немає \r\n"
        + (f"        Загалом днів співпраці: {tenure}\r\n" if tenure is not None else ""))
    fields = list(cf or [])
    if date:
        fields.append({"id": 30, "name": "Termination date", "value": date})
    return {"id": id_, "tracker": {"id": tracker, "name": "GA | Leaver"}, "status": {"id": 1, "name": "New"},
            "subject": f"GA | Leaver | {fio} | {subject_date or ''}",
            "description": d, "custom_fields": fields}


def person(sam, gn, sn, ou=OU, uac="512", created=None):
    p = {"dn": f"CN={gn} {sn},OU=linear_staff,{ou}" if ou == OU else f"CN={gn} {sn},{ou}", "sAMAccountName": sam,
            "givenName": gn, "sn": sn, "displayName": f"{gn} {sn}", "cn": f"{gn} {sn}", "userAccountControl": uac}
    if created:
        p["whenCreated"] = created
    return p


def fetch(*iss):
    return [{"issues": list(iss), "total_count": len(iss), "offset": 0, "limit": 100}]


def ldap(login, dn, uac="512"):
    return {login: [{"dn": dn, "userAccountControl": uac}]}


def by(m):
    return {"__by_login": m}


GW204 = {"statusCode": 204, "body": ""}
GW404 = {"statusCode": 404, "body": {"error": {"code": 404, "message": "Resource Not Found: userKey"}}}
GW500 = {"statusCode": 500, "body": {"error": {"code": 500, "message": "Backend Error"}}}
GW403 = {"statusCode": 403, "body": {"error": {"code": 403, "message": "Not Authorized to access this resource/api"}}}

cases = [
    {"name": "регресія 13.10: порожній «AD -» -> знайдено в AD за ПІБ (єдиний збіг), обробка",
     "stubs": {F: fetch(issue(50462, login="", fio="Щербак Юлія Петрівна")),
               LS: by({"Shcherbak": [person("y.shcherbak", "Yuliia", "Shcherbak")]}), GW: by({"Shcherbak": GW204})},
     "counts": {CMISS: 0, UP: 1, MV: 1, CLOSE: 1, SHEET: 1},
     "has": {"Code: Parse Tickets": [{"lookup": "name", "sn": "Shcherbak", "gn": "Yuliia", "ldap_filter": "~(sn=Shcherbak)"}],
             DEC: [{"login": "y.shcherbak", "found_by_name": True, "guest_email": "y.shcherbak_example.com@tenant.example.org.guest.google"}],
             CLOSE: [{"note": "~знайдено в AD за ПІБ"}], SHEET: [{"login": "y.shcherbak"}]}},
    {"name": "порожній «AD -» і немає ПІБ: коментар", "stubs": {F: fetch(issue(50461, login="", fio=""))},
     "counts": {CMISS: 1, LS: 0, CLOSE: 0}, "has": {CMISS: [{"id": 50461, "note": "~AD-логін не вказано"}]}},
    {"name": "транслітерація КМУ-2010: Є/Ї/Й/Ю/Я на початку, зг, ь, апостроф",
     "stubs": {F: fetch(issue(201, login="", fio="Ярошенко Ольга"), issue(202, login="", fio="Згурський Йосип"),
                        issue(203, login="", fio="Їжакевич Мар'яна"), issue(204, login="", fio="Юрченко Євген"),
                        issue(205, login="", fio="Гончарний Юлія"))},
     "has": {"Code: Parse Tickets": [{"sn": "Yaroshenko", "gn": "Olha"}, {"sn": "Zghurskyi", "gn": "Yosyp"},
             {"sn": "Yizhakevych", "gn": "Mariana"}, {"sn": "Yurchenko", "gn": "Yevhen"}, {"sn": "Honcharnyi", "gn": "Yuliia"}]}},
    {"name": "префікс «ФОП» перед ПІБ відкидається",
     "stubs": {F: fetch(issue(211, login="", fio="ФОП Москаленко Вікторія Ігорівна"))},
     "has": {"Code: Parse Tickets": [{"sn": "Moskalenko", "gn": "Viktoriia", "fio": "Москаленко Вікторія Ігорівна"}]}},
    {"name": "ПІБ лише з теми, якщо рядка «ГА -» немає",
     "stubs": {F: fetch(issue(206, login="", fio="Сидоренко Олег", desc="Запит на розірвання. \r\n AD - \r\n тел: +380000000206"))},
     "has": {"Code: Parse Tickets": [{"sn": "Sydorenko", "gn": "Oleh", "lookup": "name"}]}},
    {"name": "за ПІБ два активні збіги: нічого не блокуємо, кандидати в коментарі",
     "stubs": {F: fetch(issue(207, login="", fio="Коваль Іван")),
               LS: by({"Koval": [person("i.koval", "Ivan", "Koval"), person("ivan.koval", "Ivan", "Koval"), person("p.koval", "Petro", "Koval")]})},
     "counts": {UP: 0, GW: 0, CLOSE: 0, CPROB: 1},
     "has": {CPROB: [{"id": 207, "note": "~i.koval (linear_staff, активний); ivan.koval (linear_staff, активний)"}]}},
    {"name": "за ПІБ активний + заблокований дублікат: беремо активного, дублікат у звіті",
     "stubs": {F: fetch(issue(214, login="", fio="Тестер Адам")),
               LS: by({"Tester": [person("a.tester", "Adam", "Tester", ou="OU=Client,OU=AllUsers,OU=COMPANY,DC=example,DC=com", uac="514"),
                                 person("adam.tester", "Adam", "Tester")]}), GW: by({"Tester": GW204})},
     "counts": {UP: 1, MV: 1, CLOSE: 1, CPROB: 0},
     "has": {DEC: [{"login": "adam.tester", "found_by_name": True}], CLOSE: [{"note": "~пропущені: a.tester (Client, заблокований)"}]}},
    {"name": "за ПІБ усі збіги заблоковані (два): стоп, кандидати в коментарі",
     "stubs": {F: fetch(issue(215, login="", fio="Петренко Андрій")),
               LS: by({"Petrenko": [person("a.petrenko", "Andrii", "Petrenko", uac="514"), person("andrii.petrenko", "Andrii", "Petrenko", uac="514")]})},
     "counts": {UP: 0, GW: 0, CPROB: 1}, "has": {CPROB: [{"note": "~знайдено кілька акаунтів"}]}},
    {"name": "латиниця ЗАГЛАВНИМИ з трьох слів (реальна заявка): шукаємо «перше + останнє», знаходимо Adam Tester",
     "stubs": {F: fetch(issue(216, login="", fio="ADAM LEOPOLD TESTER")),
               LS: by({"Tester": [person("adam.tester", "Adam", "Tester")]}), GW: by({"Tester": GW204})},
     "counts": {UP: 1, CLOSE: 1},
     "has": {"Code: Parse Tickets": [{"gn": "Adam", "sn": "Tester", "pairs": [["Adam", "Tester"], ["Tester", "Adam"], ["Adam", "Leopold"], ["Leopold", "Adam"]]}],
             DEC: [{"login": "adam.tester", "found_by_name": True}]}},
    {"name": "термін співпраці збігається з датою створення лише одного з двох активних: беремо його, перевірка в звіті",
     "stubs": {F: fetch(issue(221, login="", fio="Тестер Адам", tenure=24)),
               LS: by({"Tester": [person("a.tester", "Adam", "Tester", created="$AD_CREATED_60"),
                                 person("adam.tester", "Adam", "Tester", created="$AD_CREATED_24")]}), GW: by({"Tester": GW204})},
     "counts": {UP: 1, CLOSE: 1},
     "has": {DEC: [{"login": "adam.tester"}], CLOSE: [{"note": "~перевірено за датою створення"}, {"note": "~a.tester (linear_staff, активний), створено"}]}},
    {"name": "термін співпраці не збігається з жодним акаунтом з таким іменем: стоп, коментар з датами",
     "stubs": {F: fetch(issue(222, login="", fio="Коваль Іван", tenure=24)),
               LS: by({"Koval": [person("i.koval", "Ivan", "Koval", created="$AD_CREATED_300")]})},
     "counts": {UP: 0, GW: 0, CLOSE: 0, CPROB: 1},
     "has": {CPROB: [{"note": "~дата його створення не збігається з тривалістю співпраці"}]}},
    {"name": "термін співпраці збігається з єдиним акаунтом (допуск 3 дні): блокуємо",
     "stubs": {F: fetch(issue(223, login="", fio="Іваненко Петро", tenure=24)),
               LS: by({"Ivanenko": [person("p.ivanenko", "Petro", "Ivanenko", created="$AD_CREATED_26")]}), GW: by({"Ivanenko": GW204})},
     "counts": {UP: 1, CLOSE: 1}},
    {"name": "термін співпраці є, два акаунти підходять за датою: стоп (неоднозначно)",
     "stubs": {F: fetch(issue(224, login="", fio="Сидоренко Олег", tenure=24)),
               LS: by({"Sydorenko": [person("o.sydorenko", "Oleh", "Sydorenko", created="$AD_CREATED_24"), person("oleh.sydorenko", "Oleh", "Sydorenko", created="$AD_CREATED_25")]})},
     "counts": {UP: 0, CPROB: 1}, "has": {CPROB: [{"note": "~знайдено кілька акаунтів"}]}},
    {"name": "латиниця з двох слів: «Ім'я Прізвище»",
     "stubs": {F: fetch(issue(217, login="", fio="John Smith")), LS: by({"Smith": [person("john.smith", "John", "Smith")]}), GW: by({"Smith": GW204})},
     "counts": {CLOSE: 1}, "has": {DEC: [{"login": "john.smith"}]}},
    {"name": "латиниця: порядок «Прізвище Ім'я» в заявці, в AD навпаки: теж знаходимо",
     "stubs": {F: fetch(issue(218, login="", fio="SMITH JOHN")), LS: by({"John": [person("john.smith", "John", "Smith")]}), GW: by({"John": GW204})},  # ключ заглушки = прізвище першої пари («Smith John» -> John)
     "counts": {CLOSE: 1}},
    {"name": "латиниця: людини немає в AD, коментар з варіантами імені",
     "stubs": {F: fetch(issue(219, login="", fio="NOBODY NOWHERE")), LS: by({})},
     "counts": {UP: 0, CPROB: 1}, "has": {CPROB: [{"note": "~варіанти латиницею: Nobody Nowhere / Nowhere Nobody"}]}},
    {"name": "змішані алфавіти в імені (кирилиця + латиниця): ПІБ не розпізнано, коментар",
     "stubs": {F: fetch(issue(220, login="", fio="Adam Матум"))},
     "counts": {CMISS: 1, LS: 0}},
    {"name": "за ПІБ лише однофамільці: не знайдено, підказка в коментарі",
     "stubs": {F: fetch(issue(208, login="", fio="Бондар Олена")), LS: by({"Bondar": [person("t.bondar", "Taras", "Bondar")]})},
     "counts": {UP: 0, GW: 0, CPROB: 1}, "has": {CPROB: [{"note": "~З таким прізвищем є: Taras Bondar: t.bondar"}]}},
    {"name": "за ПІБ: ім'я в AD іншим регістром теж збіг",
     "stubs": {F: fetch(issue(209, login="", fio="Мельник Анна")), LS: by({"Melnyk": [person("a.melnyk", "ANNA", "MELNYK")]}),
               GW: by({"Melnyk": GW204})},
     "counts": {CLOSE: 1}, "has": {DEC: [{"login": "a.melnyk"}]}},
    {"name": "за ПІБ: ім'я/прізвище в AD порожні, знайдено за шаблоном логіна ms.і.прізвище",
     "stubs": {F: fetch(issue(212, login="", fio="Логвінов Олексій")),
               LS: by({"Lohvinov": [{"dn": f"CN=ms.o.lohvinov,OU=linear_staff,{OU}", "sAMAccountName": "ms.o.lohvinov", "givenName": [], "sn": [], "userAccountControl": "512"}]}),
               GW: by({"Lohvinov": GW204})},
     "counts": {CLOSE: 1}, "has": {DEC: [{"login": "ms.o.lohvinov", "found_by_login_pattern": True}], CLOSE: [{"note": "~знайдено за шаблоном логіна"}]}},
    {"name": "за ПІБ: логін за шаблоном, але прізвище в AD інше -> не беремо",
     "stubs": {F: fetch(issue(213, login="", fio="Логвінов Олексій")),
               LS: by({"Lohvinov": [{"dn": f"CN=Other,{OU}", "sAMAccountName": "o.lohvinov", "givenName": "Olha", "sn": "Lohvinova", "userAccountControl": "512"}]})},
     "counts": {UP: 0, CPROB: 1}, "has": {DEC: [{"ad_status": "name_not_found"}]}},
    {"name": "за ПІБ: єдиний збіг поза AllUsers не блокуємо",
     "stubs": {F: fetch(issue(210, login="", fio="Ткач Ігор")),
               LS: by({"Tkach": [{**person("i.tkach", "Ihor", "Tkach"), "dn": "CN=Ihor Tkach,OU=Admins,OU=COMPANY,DC=example,DC=com"}]})},
     "counts": {UP: 0, CPROB: 1}, "has": {CPROB: [{"note": "~поза OU=AllUsers"}]}},
    {"name": "щасливий шлях: блокування, перенос, гостя видалено, заявку закрито",
     "stubs": {F: fetch(issue(101, "ivan.test")), LS: by(ldap("ivan.test", f"CN=Ivan Test,{OU}")), GW: by({"ivan.test": GW204})},
     "counts": {UP: 1, MV: 1, GW: 1, CLOSE: 1, SHEET: 1, CPROB: 0, CMISS: 0},
     "has": {DEC: [{"ad_status": "disable", "new_uac": "514", "target_dn": f"CN=Ivan Test,{FIRED}",
                    "guest_email": "ivan.test_example.com@tenant.example.org.guest.google"}],
             CLOSE: [{"id": 101, "note": "~Гостьовий запис видалено"}]}},
    {"name": "інші прапорці userAccountControl зберігаються (66048 -> 66050)",
     "stubs": {F: fetch(issue(102, "keep.flags")), LS: by(ldap("keep.flags", f"CN=Keep Flags,OU=Sub,{OU}", "66048")), GW: by({"keep.flags": GW204})},
     "has": {DEC: [{"new_uac": "66050", "target_dn": f"CN=Keep Flags,{FIRED}"}]}},
    {"name": "кома в CN екранована: правильний новий DN",
     "stubs": {F: fetch(issue(103, "comma.cn")), LS: by(ldap("comma.cn", f"CN=Test\\, Comma,{OU}")), GW: by({"comma.cn": GW204})},
     "has": {DEC: [{"target_dn": f"CN=Test\\, Comma,{FIRED}"}]}},
    {"name": "дата в майбутньому: нічого не робимо", "stubs": {F: fetch(issue(104, "future.user", date="$TOMORROW"))},
     "counts": {LS: 0, CMISS: 0, CLOSE: 0}},
    {"name": "дата сьогодні: обробляємо",
     "stubs": {F: fetch(issue(105, "today.user", date="$TODAY")), LS: by(ldap("today.user", f"CN=Today,{OU}")), GW: by({"today.user": GW204})},
     "counts": {CLOSE: 1}},
    {"name": "немає дати ніде: коментар", "stubs": {F: fetch(issue(106, "nodate.user", date=None))},
     "counts": {CMISS: 1, LS: 0}, "has": {CMISS: [{"note": "~не вказано дату звільнення"}]}},
    {"name": "дата з теми, якщо полів немає",
     "stubs": {F: fetch(issue(107, "subj.date", date=None, subject_date="$YESTERDAY")), LS: by(ldap("subj.date", f"CN=Subj,{OU}")), GW: by({"subj.date": GW204})},
     "counts": {CLOSE: 1}},
    {"name": "логін кирилицею: неприпустимий формат", "stubs": {F: fetch(issue(108, "Іван Тест"))},
     "counts": {CMISS: 1, LS: 0}, "has": {CMISS: [{"note": "~неприпустимий формат"}]}},
    {"name": "логін з кастомного поля 87, якщо в описі немає",
     "stubs": {F: fetch(issue(109, desc="ПІБ - Без Рядка\r\nТел: +380000000109", cf=[{"id": 87, "name": "AD login", "value": "cf.login"}])),
               LS: by(ldap("cf.login", f"CN=CF,{OU}")), GW: by({"cf.login": GW204})},
     "counts": {CLOSE: 1}, "has": {DEC: [{"login": "cf.login"}]}},
    {"name": "логін у форматі пошти: sAMAccountName без домену",
     "stubs": {F: fetch(issue(110, "mail.user@example.com")), LS: by(ldap("mail.user", f"CN=Mail,{OU}")), GW: by({"mail.user": GW204})},
     "has": {DEC: [{"login": "mail.user", "guest_email": "mail.user_example.com@tenant.example.org.guest.google"}]}},
    {"name": "інший трекер ігнорується", "stubs": {F: fetch(issue(111, "other.tracker", tracker=25))},
     "counts": {LS: 0, CMISS: 0}},
    {"name": "немає в AD і немає гостя (404): імовірно видалено за неактивність, закриваємо",
     "stubs": {F: fetch(issue(112, "ghost.user")), LS: by({}), GC: by({"ghost.user": GW404})},
     "counts": {GC: 1, GW: 0, UP: 0, CLOSE: 1, SHEET: 1, CPROB: 0},
     "has": {CLOSE: [{"id": 112, "note": "~видалено автоматично"}], SHEET: [{"login": "ghost.user"}]}},
    {"name": "немає в AD, а гість є: нічого не видаляємо, коментар",
     "stubs": {F: fetch(issue(130, "half.ghost")), LS: by({}), GC: by({"half.ghost": {"statusCode": 200, "body": {"primaryEmail": "x"}}})},
     "counts": {GW: 0, CLOSE: 0, CPROB: 1}, "has": {CPROB: [{"id": 130, "note": "~гостьовий акаунт у Google є"}]}},
    {"name": "немає в AD, гість 403 і доступ до Google працює: гостя немає, закриваємо",
     "stubs": {F: fetch(issue(132, "gone.403")), LS: by({}), GC: by({"gone.403": GW403})},
     "counts": {CLOSE: 1, CPROB: 0}, "has": {CLOSE: [{"note": "~не існує (Google: 403)"}]}},
    {"name": "немає в AD, гість 403, але доступ до Google не працює: коментар, не закриваємо",
     "stubs": {F: fetch(issue(131, "gc.fail")), LS: by({}), GC: by({"gc.fail": GW403}), "[Google] Check API Access": {"statusCode": 403}},
     "counts": {CLOSE: 0, CPROB: 1}, "has": {CPROB: [{"note": "~перевірити не вдалося (403)"}]}},
    {"name": "кілька акаунтів: коментар, нічого не блокуємо",
     "stubs": {F: fetch(issue(113, "dup.user")), LS: by({"dup.user": [{"dn": f"CN=Dup1,{OU}", "userAccountControl": "512"}, {"dn": f"CN=Dup2,{OU}", "userAccountControl": "512"}]})},
     "counts": {UP: 0, CPROB: 1}, "has": {CPROB: [{"note": "~кілька акаунтів"}]}},
    {"name": "поза OU=AllUsers: не блокуємо, коментар",
     "stubs": {F: fetch(issue(114, "admin.user")), LS: by(ldap("admin.user", "CN=Admin,OU=Admins,OU=COMPANY,DC=example,DC=com"))},
     "counts": {UP: 0, GW: 0, CPROB: 1}, "has": {CPROB: [{"note": "~поза OU=AllUsers"}]}},
    {"name": "уже в «Уволенные» і заблокований: AD пропускаємо, Google видаляємо, закриваємо",
     "stubs": {F: fetch(issue(115, "done.user")), LS: by(ldap("done.user", f"CN=Done,{FIRED}", "514")), GW: by({"done.user": GW204})},
     "counts": {UP: 0, MV: 0, GW: 1, CLOSE: 1}, "has": {CLOSE: [{"note": "~уже був заблокований"}]}},
    {"name": "в «Уволенные», але активний: коментар для ручної дії",
     "stubs": {F: fetch(issue(116, "half.user")), LS: by(ldap("half.user", f"CN=Half,{FIRED}", "512"))},
     "counts": {UP: 0, GW: 0, CPROB: 1}, "has": {CPROB: [{"note": "~не заблокований"}]}},
    {"name": "гостя не було (404): закриваємо",
     "stubs": {F: fetch(issue(117, "noguest.user")), LS: by(ldap("noguest.user", f"CN=NoGuest,{OU}")), GW: by({"noguest.user": GW404})},
     "counts": {CLOSE: 1, SHEET: 1}, "has": {CLOSE: [{"note": "~не було (404)"}]}},
    {"name": "видалення гостя 403 і доступ працює: гостя не було, закриваємо",
     "stubs": {F: fetch(issue(133, "del.403")), LS: by(ldap("del.403", f"CN=Del403,{OU}")), GW: by({"del.403": GW403})},
     "counts": {CLOSE: 1}, "has": {CLOSE: [{"note": "~не було (403)"}]}},
    {"name": "Google 403 при непрацюючому доступі: заявка відкрита, коментар з причиною",
     "stubs": {F: fetch(issue(118, "gw.fail")), LS: by(ldap("gw.fail", f"CN=GwFail,{OU}")), GW: by({"gw.fail": GW403}), "[Google] Check API Access": {"statusCode": 403}},
     "counts": {CLOSE: 0, SHEET: 0, CPROB: 1}, "has": {CPROB: [{"id": 118, "note": "~НЕ видалено (403): Not Authorized"}]}},
    {"name": "помилка LDAP update: коментар ad_error, Google не чіпаємо",
     "stubs": {F: fetch(issue(119, "ldap.fail")), LS: by(ldap("ldap.fail", f"CN=LdapFail,{OU}")), UP: by({"ldap.fail": {"__throw": "Insufficient access rights"}})},
     "counts": {MV: 0, GW: 0, CPROB: 1}, "has": {CPROB: [{"note": "~Insufficient access rights"}]}},
    {"name": "помилка LDAP rename: коментар ad_error",
     "stubs": {F: fetch(issue(120, "mv.fail")), LS: by(ldap("mv.fail", f"CN=MvFail,{OU}")), MV: by({"mv.fail": {"__throw": "No such object"}})},
     "counts": {GW: 0, CPROB: 1}, "has": {CPROB: [{"note": "~No such object"}]}},
    {"name": "кілька заявок: ненайдений не зупиняє обробку решти",
     "stubs": {F: fetch(issue(121, "a.one"), issue(122, "b.ghost"), issue(123, "c.three"), issue(124, login="", fio="")),
               LS: by({**ldap("a.one", f"CN=A,{OU}"), **ldap("c.three", f"CN=C,{OU}")}),
               GW: by({"a.one": GW204, "c.three": GW404}), GC: by({"b.ghost": GW404})},
     "counts": {LS: 3, CLOSE: 3, SHEET: 3, CPROB: 0, CMISS: 1},
     "has": {CLOSE: [{"id": 121}, {"id": 122, "note": "~видалено автоматично"}, {"id": 123}], CMISS: [{"id": 124}]}},
    {"name": "Redmine віддає кожну заявку окремим елементом",
     "stubs": {F: [issue(125, "per.item")], LS: by(ldap("per.item", f"CN=PerItem,{OU}")), GW: by({"per.item": GW204})},
     "counts": {CLOSE: 1}},
    {"name": "без спаму: та сама проблема двічі = один коментар, після виправлення обробка",
     "steps": [
         {"stubs": {F: fetch(issue(126, login="", fio=""))}, "counts": {CMISS: 1}},
         {"stubs": {F: fetch(issue(126, login="", fio=""))}, "counts": {CMISS: 0, LS: 0}},
         {"stubs": {F: fetch(issue(126, "fixed.user")), LS: by(ldap("fixed.user", f"CN=Fixed,{OU}")), GW: by({"fixed.user": GW204})},
          "counts": {CMISS: 0, CLOSE: 1}}]},
    {"name": "без спаму: Google 500 два дні = один коментар; потім AD already_done і закриття",
     "steps": [
         {"stubs": {F: fetch(issue(127, "gw.retry")), LS: by(ldap("gw.retry", f"CN=GwRetry,{OU}")), GW: by({"gw.retry": GW500})},
          "counts": {CPROB: 1, UP: 1}},
         {"stubs": {F: fetch(issue(127, "gw.retry")), LS: by(ldap("gw.retry", f"CN=GwRetry,{FIRED}", "514")), GW: by({"gw.retry": GW500})},
          "counts": {CPROB: 0, UP: 0, GW: 1}},
         {"stubs": {F: fetch(issue(127, "gw.retry")), LS: by(ldap("gw.retry", f"CN=GwRetry,{FIRED}", "514")), GW: by({"gw.retry": GW204})},
          "counts": {CLOSE: 1}}]},
]

HC = "[Google] Check API Access"
for c in cases:
    for st in (c.get("steps") or [c]):
        st.setdefault("stubs", {}).setdefault(HC, {"statusCode": 200})

Path(__file__).with_name("cases_linear.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(cases), "cases")
