// Розбір заявок «GA | Leaver» (трекер 41): AD-логін, дата звільнення, гостьова пошта Google.
// Вихід: action = 'process' (готово до обробки) або 'notify' (у заявці бракує даних, треба коментар).
// Коментар про ту саму проблему пишеться один раз (пам'ять у static data флоу).
const TRACKER_ID = 41;
const LOGIN_CF_ID = 87;      // кастомне поле «AD login»
const TERM_DATE_CF_ID = 30;  // кастомне поле «Termination date»
const LOGIN_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})?$/;

const state = $getWorkflowStaticData('global');
state.notified_input = state.notified_input || {};
state.notified_run = state.notified_run || {};

const today = DateTime.now().setZone('Europe/Kyiv').toISODate();
// Доступ до Google API працює? Тоді 403 на конкретного гостя означає «гостя немає» (див. final_report.js).
const hc = $('[Google] Check API Access').first().json;
const gw_ok = Number(hc.statusCode) === 200;

let issues = [];
for (const it of $input.all()) {
  if (Array.isArray(it.json.issues)) issues.push(...it.json.issues);
  else if (it.json && it.json.id) issues.push(it.json);
}

const cf = (issue, id, name) => (issue.custom_fields || []).find(f => f.id === id || f.name === name);

// Транслітерація за постановою КМУ №55 (2010), як імена записані в AD (Зразковий Олег -> Zrazkovyi Oleh).
const TR = { а:'a', б:'b', в:'v', г:'h', ґ:'g', д:'d', е:'e', є:'ie', ж:'zh', з:'z', и:'y', і:'i', ї:'i', й:'i', к:'k', л:'l',
  м:'m', н:'n', о:'o', п:'p', р:'r', с:'s', т:'t', у:'u', ф:'f', х:'kh', ц:'ts', ч:'ch', ш:'sh', щ:'shch', ь:'', ю:'iu', я:'ia',
  ы:'y', э:'e', ё:'io', ъ:'' };
const TR_START = { є:'ye', ї:'yi', й:'y', ю:'yu', я:'ya', ё:'yo' };
function translit(word) {
  const w = word.toLowerCase().replace(/[’'ʼ`]/g, '').replace(/зг/g, 'zgh');
  let out = '';
  for (let i = 0; i < w.length; i++) {
    const c = w[i];
    out += (i === 0 && TR_START[c]) || (TR[c] !== undefined ? TR[c] : c);
  }
  return out.charAt(0).toUpperCase() + out.slice(1);
}
// Шаблони логінів в AD (запасний пошук, якщо в акаунта не заповнені ім'я/прізвище):
// ім'я.прізвище, і.прізвище, ms.і.прізвище, ms.ім'я.прізвище (ms. у старих акаунтів).
const loginVariants = (g, s) => {
  const G = g.toLowerCase().replace(/[^a-z-]/g, ''), S = s.toLowerCase().replace(/[^a-z-]/g, '');
  if (!G || !S) return [];
  return [`${G}.${S}`, `${G[0]}.${S}`, `ms.${G[0]}.${S}`, `ms.${G}.${S}`];
};
const ldapEsc = s => s.replace(/[\\*()\0]/g, c => '\\' + c.charCodeAt(0).toString(16).padStart(2, '0'));

function parseName(issue) {
  // Рядок «ГА - Прізвище Ім'я По батькові» в описі, інакше третій сегмент теми «GA | Leaver | ПІБ | дата».
  const m = (issue.description || '').match(/(?:^|[\s|])ГА[ \t]*[-–—:][ \t]*([^\r\n]*)/);
  const fio = ((m && m[1]) || (issue.subject || '').split('|')[2] || '').trim().replace(/^(ФОП|ФЛП)\s+/i, '');
  const parts = fio.split(/\s+/).filter(p => /^[А-Яа-яЁёЄєІіЇїҐґ’'ʼ-]+$/.test(p));
  if (parts.length < 2) return null;
  return { fio, sn: translit(parts[0]), gn: translit(parts[1]) };
}

function parseLogin(issue) {
  // Рядок «AD - login» в описі. [ \t]* замість \s*, щоб не перескочити на наступний рядок.
  const m = (issue.description || '').match(/(?:^|[\s|])AD[ \t]*[-–—:][ \t]*([^\r\n]*)/i);
  let raw = m ? m[1].trim() : '';
  if (!raw) {
    const f = cf(issue, LOGIN_CF_ID, 'AD login');
    raw = f && f.value ? String(f.value).trim() : '';
  }
  if (!raw) return { reason: 'no_login' };
  const login = raw.split(/\s+/)[0];
  if (!LOGIN_RE.test(login)) return { reason: 'bad_login', value: raw };
  return { login };
}

function parseDate(issue) {
  const f = cf(issue, TERM_DATE_CF_ID, 'Termination date');
  let d = (f && f.value) || issue.due_date || ((issue.subject || '').match(/(\d{4}-\d{2}-\d{2})/) || [])[1] || '';
  d = String(d).trim();
  if (!d) return { reason: 'no_date' };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || !DateTime.fromISO(d).isValid) return { reason: 'bad_date', value: d };
  return { date: d };
}

// [що перевірено, результат, що робити далі]
const NOTES = {
  no_login: () => ['• Рядок «AD -» в описі: порожній.\n• Поле «AD login»: порожнє.\n• ПІБ (рядок «ГА -» або тема заявки): не знайдено, тому пошук в AD за ПІБ неможливий.',
    'AD-логін не вказано, і знайти працівника в AD немає за чим.',
    ['впишіть логін у рядок «AD -» (або ПІБ у рядок «ГА -»), і автоматизація обробить заявку сама;',
     'якщо акаунта в AD немає, перевірте гостьовий акаунт Google і закрийте заявку вручну.']],
  bad_login: v => [`• Рядок «AD -» в описі: «${v}».`,
    `AD-логін «${v}» має неприпустимий формат (очікується латиниця без пробілів, наприклад ivan.petrenko).`,
    ['виправте логін у рядку «AD -», і автоматизація обробить заявку сама.']],
  no_date: () => ['• Поле «Termination date»: порожнє.\n• Due date: порожня.\n• Дата в темі заявки (РРРР-ММ-ДД): немає.',
    'не вказано дату звільнення, тому невідомо, коли закривати доступи.',
    ['заповніть «Termination date» (РРРР-ММ-ДД); у день звільнення або пізніше автоматизація обробить заявку сама.']],
  bad_date: v => [`• Дата звільнення в заявці: «${v}».`,
    `дату «${v}» не вдалося розпізнати (очікується формат РРРР-ММ-ДД).`,
    ['виправте дату в полі «Termination date», і автоматизація обробить заявку сама.']],
};
const fmt = ([checked, result, next]) =>
  `⚠ Автоматичний offboarding не виконано.\n\nЩо перевірено:\n${checked}\n\nРезультат: ${result}\n\n` +
  `Що робити далі:\n${next.map((s, i) => `${i + 1}. ${s.charAt(0).toUpperCase()}${s.slice(1)}`).join('\n')}\n\n` +
  'Заявку залишено відкритою. Нічого в AD і Google не змінено. Автоматизація перевіряє заявку щодня о 18:00; про ту саму проблему повторно не пише.';

const results = [];
const openIds = new Set();
for (const issue of issues) {
  if (!issue || !issue.tracker || issue.tracker.id !== TRACKER_ID) continue;
  const id = issue.id;
  openIds.add(String(id));
  let L = parseLogin(issue);
  const D = parseDate(issue);

  // Дата в майбутньому: просто чекаємо, нічого не пишемо.
  if (D.date && D.date > today) continue;

  // Логіна немає: шукатимемо в AD за ПІБ (рішення приймає Decide AD Action).
  const N = L.reason === 'no_login' ? parseName(issue) : null;
  if (N) L = { name: N };

  const problem = L.reason ? L : (D.reason ? D : null);
  if (problem) {
    const key = problem.reason + ':' + (problem.value || '');
    if (state.notified_input[id] === key) continue;
    state.notified_input[id] = key;
    results.push({ json: {
      action: 'notify', id, reason: problem.reason, subject: issue.subject || '',
      note: fmt(NOTES[problem.reason](problem.value)),
    } });
    continue;
  }

  delete state.notified_input[id];
  if (L.name) {
    results.push({ json: {
      action: 'process', gw_ok, id, lookup: 'name', login: '', guest_email: '', leaver_date: D.date, subject: issue.subject || '',
      fio: L.name.fio, sn: L.name.sn, gn: L.name.gn,
      login_variants: loginVariants(L.name.gn, L.name.sn),
      ldap_filter: `(&(objectClass=user)(|(sn=${ldapEsc(L.name.sn)})` +
        loginVariants(L.name.gn, L.name.sn).map(v => `(sAMAccountName=${ldapEsc(v)})`).join('') + '))',
    } });
    continue;
  }
  const email = L.login.includes('@') ? L.login : `${L.login}@example.com`;
  const sam = email.split('@')[0];
  const guest = email.endsWith('.guest.google') ? email : `${email.replace('@', '_')}@tenant.example.org.guest.google`;
  results.push({ json: {
    action: 'process', gw_ok, id, lookup: 'login', login: sam, guest_email: guest, leaver_date: D.date, subject: issue.subject || '',
    ldap_filter: `(&(objectClass=user)(sAMAccountName=${ldapEsc(sam)}))`,
  } });
}

// Забуваємо закриті заявки.
for (const k of Object.keys(state.notified_input)) if (!openIds.has(k)) delete state.notified_input[k];
for (const k of Object.keys(state.notified_run)) if (!openIds.has(k)) delete state.notified_run[k];

return results;
