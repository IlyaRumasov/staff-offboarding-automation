// Підсумок по заявці після кроку Google: текст звіту і рішення, чи закривати заявку.
// Сюди приходить відповідь Google з двох гілок: видалення гостя (AD заблоковано або вже було) і перевірка гостя (в AD акаунта немає).
// Закриваємо, якщо гостя видалено (2xx) або його не було (404, або 403 при робочому доступі до API). Інакше коментар, заявка відкрита;
// наступного дня AD уже «already_done», тож повториться лише крок Google. Той самий коментар двічі не пишемо.
const d = $('Code: Decide AD Action').first().json;
const r = $input.first().json;
const state = $getWorkflowStaticData('global');
state.notified_run = state.notified_run || {};

const code = Number(r.statusCode || (r.error && (r.error.httpCode || r.error.status)) || 0);
// Для сервісного акаунта «Google service account (guests)» неіснуючий гість дає 403, а не 404 (перевірено 14.10.2026:
// наявний гість 200, вигаданий 403). Тому 403 = «гостя немає», лише якщо на початку запуску доступ до API працював.
const gone = code === 404 || (code === 403 && d.gw_ok === true);
const msg = (r.body && r.body.error && r.body.error.message) || (r.error && (r.error.message || r.error.description)) || r.statusMessage || 'невідома помилка';
const tail = 'Автоматизація перевіряє заявку щодня о 18:00; про ту саму проблему повторно не пише.';
const adminFix = '1. Перевірте права сервісного акаунта Google (User Management Admin) і ключ у кредах n8n «Google service account (guests)».\n';

let out;
if (d.ad_status === 'not_found') {
  // Логін є, в AD акаунта немає. Гостя теж немає: записів ніде немає, імовірно видалено автоматично за неактивність.
  const checkedAd = `• Active Directory: пошук за логіном «${d.login}» по всьому домену, включно з OU «Уволенные»: акаунта немає.`;
  if (gone) {
    delete state.notified_run[d.id];
    out = { id: d.id, close: true, notify: false, login: d.login, guest_email: d.guest_email, leaver_date: d.leaver_date,
      note: 'Автоматичний offboarding: доступів не знайдено, заявку закрито.\n\n' +
            `Що перевірено:\n${checkedAd}\n• Google Workspace: гостьовий акаунт ${d.guest_email}: не існує (Google: ${code}).\n\n` +
            'Висновок: записів про працівника немає ні в AD, ні в Google. Найімовірніше, акаунт було видалено автоматично ' +
            'через тривалу неактивність. Закривати нічого.\n\n' +
            'Архівування: запис додано до архівного реєстру Google Sheets.' };
  } else {
    const exists = code >= 200 && code < 300;
    const key = exists ? 'nf_guest_exists' : 'nf_gw_error:' + code;
    const notify = state.notified_run[d.id] !== key;
    state.notified_run[d.id] = key;
    out = { id: d.id, close: false, notify,
      note: '⚠ Автоматичний offboarding не виконано.\n\n' +
            `Що перевірено:\n${checkedAd}\n• Google Workspace: гостьовий акаунт ${d.guest_email}: ` +
            (exists ? 'існує.' : `перевірити не вдалося (${code || 'немає відповіді'}): ${msg}.`) + '\n\n' +
            (exists
              ? 'Результат: в AD акаунта немає, а гостьовий акаунт у Google є. Так не має бути, тому автоматично нічого не видалено.\n\n' +
                'Що робити далі:\n1. Перевірте, чи правильний логін у рядку «AD -» (можлива помилка в логіні).\n' +
                '2. Якщо логін правильний, видаліть гостьовий акаунт вручну і закрийте заявку.\n\n'
              : 'Результат: не вдалося перевірити Google, тому заявку не закрито.\n\n' +
                `Що робити далі:\n${adminFix}2. Автоматизація повторить перевірку під час наступного запуску.\n\n`) +
            'Заявку залишено відкритою. Нічого в AD і Google не змінено. ' + tail };
  }
} else {
  // AD заблоковано (щойно або раніше), результат видалення гостя.
  let gw, gwOk;
  if (code >= 200 && code < 300) { gw = 'Гостьовий запис видалено з домену.'; gwOk = true; }
  else if (gone) { gw = `Гостьового запису не було (${code}), видаляти нічого.`; gwOk = true; }
  else { gw = `НЕ видалено (${code || 'немає відповіді'}): ${msg}`; gwOk = false; }

  const ad = d.ad_status === 'already_done'
    ? 'Акаунт уже був заблокований і перебуває в OU «Уволенные».'
    : 'Акаунт заблоковано та переміщено в OU «Уволенные».';
  const body =
    `1. Active Directory:\n• Логін: ${d.login}` +
    (d.found_by_name ? ` (у заявці не вказано, знайдено в AD за ПІБ «${d.fio}»: ${d.gn} ${d.sn}, єдиний збіг` +
      (d.found_by_login_pattern ? '; ім’я/прізвище в AD не заповнені, знайдено за шаблоном логіна' : '') + ')' : '') +
    `\n• Статус: ${ad}\n` +
    `2. Google Workspace (Guest):\n• Акаунт: ${d.guest_email}\n• Статус: ${gw}\n`;

  if (gwOk) {
    delete state.notified_run[d.id];
    out = { id: d.id, close: true, notify: false, login: d.login, guest_email: d.guest_email, leaver_date: d.leaver_date,
      note: `Автоматичний offboarding успішно завершено.\nЗвіт про закриття доступів:\n${body}` +
            '3. Архівування:\n• Запис додано до архівного реєстру Google Sheets.' };
  } else {
    const key = 'gw_error:' + code;
    const notify = state.notified_run[d.id] !== key;
    state.notified_run[d.id] = key;
    const next = code === 403 || code === 401
      ? adminFix
      : '1. Перевірте гостьовий акаунт у консолі адміністратора Google Workspace і відповідь вище.\n';
    out = { id: d.id, close: false, notify,
      note: `⚠ Автоматичний offboarding завершено частково: AD виконано, Google ні.\n\n${body}\n` +
            `Що робити далі:\n${next}` +
            '2. Нічого не робіть з AD: наступного запуску автоматизація побачить, що акаунт уже заблокований, і повторить лише крок Google.\n' +
            '3. Або видаліть гостя вручну і закрийте заявку.\n\n' +
            'Заявку залишено відкритою. ' + tail };
  }
}
return [{ json: out, pairedItem: { item: 0 } }];
