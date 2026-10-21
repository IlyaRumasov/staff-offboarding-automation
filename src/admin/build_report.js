// Підсумок по заявці: звіт по кожній системі, техніка, диск, звірка логінів; рішення, чи закривати.
// Закриваємо лише коли: немає проблем, диск вирішено, IT підтвердив «Заборгованості по техніці немає».
// Якщо доступи закрито раніше і зараз нічого не змінено: короткий коментар. Той самий коментар двічі не пишемо.
const c0 = $('Code: Decide M365 Action').first().json;
const r = $input.first().json;
const m365 = { ...c0.m365 };
if (m365.status === 'delete') {
  const code = Number(r.statusCode);
  if (code >= 200 && code < 300) m365.result = 'deleted';
  else { m365.result = 'error'; m365.error = `${code || 'немає відповіді'}: ${(r.body && r.body.error && r.body.error.message) || 'не видалено'}`; }
} else m365.result = m365.status;
const c = { ...c0, m365 };
const state = $getWorkflowStaticData('global');
state.notified = state.notified || {};
const who = c.pairs[0].join(' ');
const problems = [], pending = [];
const ign = c.ad.ignored_disabled ? ` (інші акаунти з таким іменем уже заблоковані й пропущені: ${c.ad.ignored_disabled})` : '';
const pat = (c.ad.by_login_pattern ? ' (ім’я/прізвище в AD не заповнені, знайдено за шаблоном логіна)' : '') + ign;

const AD = {
  disabled: () => `Акаунт ${c.ad.login} заблоковано та переміщено в OU «Уволенные».${pat}`,
  already_done: () => `Акаунт ${c.ad.login} уже був заблокований (OU «Уволенные»).${pat}`,
  not_found: () => `Акаунт за ім'ям «${who}» не знайдено (можливо, вже видалено).`,
  multiple: () => { problems.push('AD: кілька акаунтів'); return `Знайдено кілька акаунтів: ${c.ad.candidates}. Нічого не змінено, визначте потрібний вручну.`; },
  outside_scope: () => { problems.push('AD: акаунт поза OU=AllUsers'); return `Акаунт знайдено поза OU=AllUsers (${c.ad.dn}). Нічого не змінено, потрібна ручна перевірка.`; },
  fired_but_enabled: () => { problems.push('AD: у «Уволенные», але активний'); return `Акаунт ${c.ad.login} уже в OU «Уволенные», але не заблокований. Заблокуйте вручну.`; },
  error: () => { problems.push('AD: помилка'); return `НЕ виконано (${c.ad.error}). Перевірте права сервісного облікового запису n8n в AD.`; },
};
const GOOGLE = {
  suspended: () => `Акаунт ${c.google.email} призупинено (Suspended).`,
  already_suspended: () => `Акаунт ${c.google.email} уже був призупинений.`,
  not_found: () => { problems.push('Google: акаунт не знайдено'); return `Акаунт за ім'ям «${who}» не знайдено. Якщо ім'я в Google записане інакше, призупиніть акаунт вручну; якщо акаунт уже видалено, закрийте заявку вручну.`; },
  multiple: () => { problems.push('Google: кілька акаунтів'); return `Знайдено кілька акаунтів: ${c.google.candidates}. Нічого не змінено, визначте потрібний вручну.`; },
  error: () => { problems.push('Google: помилка'); return `НЕ виконано (${c.google.error}).`; },
};
const d = c.drive;
const DRIVE = {
  transferred: () => `• Диск: перенесення запущено (кому: ${d.recipient_name}, ${d.recipient_email}).`,
  done_before: () => '• Диск: перенесення було запущено раніше.',
  not_needed: () => `• Диск: передавати не потрібно (у заявці: «${d.text}»).`,
  ask: () => { pending.push('підтвердження передачі диска');
    return `• Передати диск: ${d.recipient_name} (${d.recipient_email})?\n  У заявці: «${d.text}». Якщо так, дайте відповідь коментарем «так», і автоматизація передасть диск під час наступного запуску.`; },
  recipient_not_found: () => { pending.push('отримувач диска');
    return `• Диск: отримувача ${d.email} не знайдено в Google (або він призупинений). Вкажіть актуальний e-mail у рядку «Переадресація диску: ...».`; },
  recipient_name_not_found: () => { pending.push('отримувач диска');
    return `• Диск: кому передати, вказано як «${d.text}», але в Google такого працівника не знайдено. Вкажіть e-mail у рядку «Переадресація диску: ...».`; },
  recipient_multiple: () => { pending.push('отримувач диска');
    return `• Диск: за «${d.text}» знайдено кількох: ${d.candidates}. Вкажіть e-mail у рядку «Переадресація диску: ...».`; },
  unknown_target: () => { pending.push('отримувач диска');
    return `• Диск: не зрозуміло, кому передати (у заявці: «${d.text}»). Вкажіть e-mail у рядку «Переадресація диску: ...» або напишіть «не потрібно».`; },
  no_leaver_account: () => '• Диск: не виконувалось (акаунт Google працівника не знайдено).',
  error: () => { problems.push('Google Диск: помилка'); return `• Диск: перенесення НЕ запущено (${d.error}).`; },
};
const M365 = {
  deleted: () => `Акаунт ${c.m365.upn} видалено.`,
  not_found: () => `Акаунта за ім'ям «${who}» немає, видаляти нічого.`,
  multiple: () => { problems.push('M365: кілька акаунтів'); return `Знайдено кілька акаунтів: ${c.m365.candidates}. Нічого не видалено, визначте потрібний вручну.`; },
  error: () => { problems.push('M365: помилка'); return `НЕ виконано (${c.m365.error}).`; },
};
let eq;
if (c.equipment === 'ok') eq = 'IT підтвердив: заборгованості по техніці немає.';
else if (c.equipment === 'debt') { pending.push('повернення техніки'); eq = `За працівником числиться техніка (коментар у заявці: «${c.equipment_note.slice(0, 200)}»).`; }
else { pending.push('підтвердження IT щодо техніки'); eq = 'Підтвердження IT щодо техніки ще немає. Коли техніку перевірено, напишіть коментар «Заборгованості по техніці немає».'; }

const lines = {
  ad: AD[c.ad.result](), google: GOOGLE[c.google.result](), drive: DRIVE[d.result](), m365: M365[c.m365.result](),
};
// Звірка логінів між системами: різні логіни можуть означати, що знайдено різних людей.
const logins = [c.ad.login, (c.google.email || '').split('@')[0], (c.m365.upn || '').split('@')[0]].filter(Boolean).map(s => s.toLowerCase());
const warn = new Set(logins).size > 1 ? `\n⚠ Логіни в системах відрізняються (${[...new Set(logins)].join(', ')}). Перевірте, що це одна й та сама людина.\n` : '';

const close = !problems.length && !pending.length;
const acted = c.ad.result === 'disabled' || c.google.result === 'suspended' || d.result === 'transferred' || c.m365.result === 'deleted';
const tail = 'Автоматизація перевіряє заявку щодня о 18:00; той самий коментар повторно не пише.';

let note;
if (c.prior_report && !acted && !problems.length) {
  note = close
    ? 'Автоматичний offboarding: доступи закрито раніше (див. попередній звіт). IT підтвердив, що заборгованості по техніці немає. Заявку закрито.'
    : `Автоматичний offboarding: доступи закрито раніше (див. попередній звіт), повторно нічого не виконувалось.\nЗаявку залишено відкритою, бо очікується: ${pending.join(', ')}.\n${eq}\n${['ask', 'recipient_not_found', 'recipient_name_not_found', 'recipient_multiple', 'unknown_target'].includes(d.result) ? lines.drive + '\n' : ''}\n${tail}`;
} else {
  const head = close ? 'Автоматичний offboarding: доступи закрито, заявку закрито.'
    : problems.length ? '⚠ Автоматичний offboarding виконано частково, потрібна ручна дія.'
    : 'Автоматичний offboarding: доступи закрито, заявку залишено відкритою.';
  note = `${head}\n\nЗвіт про закриття доступів (працівник: ${c.person}):\n` +
    `1. Active Directory: ${lines.ad}\n2. Google Workspace: ${lines.google}\n${lines.drive}\n3. Microsoft 365: ${lines.m365}\n4. Техніка: ${eq}\n` + warn +
    (close ? '\nЗапис додано до архівного реєстру Google Sheets.' :
      `\nЩо залишилось: ${[...problems, ...pending].join('; ')}.\nЗаявку залишено відкритою. ${tail}`);
}

const key = (close ? 'close|' : 'open|') + note.replace(/\d{4}-\d{2}-\d{2}/g, '');
const notify = close || state.notified[c.id] !== key;
if (close) delete state.notified[c.id]; else state.notified[c.id] = key;

// В архів пишемо лише при першому закритті (не після переоткриття заявки).
return [{ json: { id: c.id, close, archive: close && !c.prior_report, notify, note, leaver_date: c.leaver_date,
  login: c.ad.login || c.google.email || c.person, google_email: c.google.email || '' }, pairedItem: { item: 0 } }];
