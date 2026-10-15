# README.md

<div align="center">
  <h1>🚀 Offboarding Automation: Redmine & AD (Admin Staff)</h1>
  <p><em>Автоматизація процесу звільнення адміністративного персоналу (Zero-Touch IT).</em></p>

## 📋 Про проєкт

Цей репозиторій містить production-ready конвеєр для платформи n8n, що автоматизує процес офбордингу (звільнення) працівників. Система повністю усуває необхідність ручного втручання IT-відділу, гарантуючи своечасне закриття доступів згідно з політиками безпеки.

Воркфлоу синхронізується з відкритими тікетами у Redmine (проєкт `staff-leavers`, Tracker ID: 25), аналізує дати звільнення та генерує масив можливих логінів. Після цього система каскадно блокує облікові записи в Active Directory, призупиняє акаунти в Google Workspace, видаляє профілі в Microsoft Entra ID та передає робочі файли на Google Drive керівнику. Після успішного виконання система оновлює тікет у Redmine та записує подію в Google Sheets.

## 🗺️ Загальна схема воркфлоу

![Offboarding Automation - Основний процес](adminoff.jpg)

### 📊 Архітектурна схема руху даних (Data Flow)

## 🚀 Архітектура та етапи роботи

* **Extract (Ingest):** Воркфлоу запускається за розкладом по буднях о 09:00, отримуючи відкриті тікети з Redmine.
* **Transform:** JS-скрипт аналізує кастомні поля, надаючи пріоритет полю Termination date (ID 30). Якщо воно порожнє — використовується `due_date` або `start_date`. Скрипт парсить email керівника для передачі прав на Drive та генерує можливі логіни користувача в системі.
* **Deprovisioning (Core):**
  * **AD:** Пошук у базовому DN `OU=administrative_staff,OU=AllUsers,OU=COMPANY,DC=example,DC=com`[cite: 3]. Блокування (`userAccountControl: 514`) та переміщення до `OU=Уволенные` через утиліту `ldapmodify`.
  * **Google:** Призупинення акаунта (Suspend) та виклик Data Transfer API для передачі прав на файли.
  * **M365:** Пошук профілю в Entra ID за ПІБ і його подальше видалення.
* **Reporting:** Формування детального звіту у Redmine, зміна статусу тікета на 17 (Закрито) та логування події (Дата, Логін, Ticket ID) до Google Sheets.

## 🛠️ Стек технологій

* **Оркестрація:** n8n
* **Логіка:** JavaScript (ES6+), Bash, LDIF
* **API:** Redmine REST API, Google Workspace Admin/Drive API, Microsoft Entra ID API, Google Sheets API

## ⚠️ Системні вимоги (Prerequisites)

1. Мережевий доступ від інстансу n8n до контролера домену (IP: `<AD_LDAPS_HOST>`, порт `636`, протокол `ldaps`).
2. Встановлені утиліти `ldap-utils` (зокрема `ldapmodify`) на хост-машині n8n.
3. Налаштована змінна оточення `LDAPTLS_REQCERT=never` для коректної роботи самопідписаних сертифікатів AD.


