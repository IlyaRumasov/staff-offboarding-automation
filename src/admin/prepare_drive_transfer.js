// Результат кроку Google (призупинення або пропуск), стан заявки з історії коментарів і запит пошуку отримувача диска.
// Стан: техніка, підтвердження передачі диска («так» після питання бота), попередні звіти бота.
// Нотатки бота впізнаємо за «Автоматичний offboarding» (старий флоу писав «Автоматичний Offboarding»).
const ctx = $('Code: Decide Google Action').first().json;
const r = $input.first().json;
const google = { ...ctx.google };
if (google.status === 'suspend') {
  const code = Number(r.statusCode);
  if (code >= 200 && code < 300 && r.body && r.body.suspended === true) google.result = 'suspended';
  else { google.result = 'error'; google.error = `${code || 'немає відповіді'}: ${(r.body && r.body.error && r.body.error.message) || (r.error && r.error.message) || 'акаунт не призупинено'}`; }
} else google.result = google.status;

const t = $('[Redmine] Get Ticket History').first().json;
const issue = t.issue || t;
const journals = (issue.journals || []).filter(j => j && j.notes);
const isBot = n => /Автоматичний\s+offboarding/i.test(n);

// Техніка: останній коментар про техніку (IT або флоу перевірки техніки в GLPI), див. src/equipment_state.js.
// @@equipment
const { equipment, equipment_note } = equipmentState(journals);

// Передача диска: питання бота «Передати диск ... (email)?» і пізніша людська відповідь «так».
let asked_email = '', confirmed_email = '', drive_done_before = false;
for (const j of journals) {
  if (isBot(j.notes)) {
    const q = j.notes.match(/Передати\s+диск[^\r\n]*?\(([^)\s]+@[^)\s]+)\)\?/i);
    if (q) { asked_email = q[1].toLowerCase(); confirmed_email = ''; }
    if (/•\s*Диск:\s*перенесення\s+запущено/i.test(j.notes)) drive_done_before = true;  // рядок зі звіту final_report.js
    if (/Google\s+Диск[\s\S]{0,400}?Успішно\s+ініційовано/i.test(j.notes)) drive_done_before = true;  // звіт старого флоу
  } else if (asked_email && /^\s*(так|да|yes|ок|ok|\+|підтверджую)(?=$|[\s.,!)])/iu.test(j.notes)) {
    confirmed_email = asked_email;
  }
}

const prior_report = journals.some(j => isBot(j.notes) && /(успішно\s+завершено|Звіт\s+про\s+закриття\s+доступів)/i.test(j.notes));


const merged = { ...ctx, google, equipment, equipment_note, asked_email, confirmed_email, drive_done_before, prior_report };

// Кого шукати в Google як отримувача диска. Без запиту, якщо передавати не треба або акаунта працівника немає.
const d = ctx.drive || {};
const base = 'https://admin.googleapis.com/admin/directory/v1/users';
const q = s => `'${String(s).replace(/'/g, "\\'")}'`;
const leaverOk = ['suspended', 'already_suspended'].includes(google.result);
let urls = [];
if (leaverOk && !drive_done_before) {
  if (d.mode === 'email') urls = [`${base}/${encodeURIComponent(d.email)}`];
  else if (['name', 'manager'].includes(d.mode)) {
    urls = confirmed_email ? [`${base}/${encodeURIComponent(confirmed_email)}`]
      : d.pairs.map(([g, s]) => `${base}?customer=my_customer&maxResults=10&query=` + encodeURIComponent(`givenName:${q(g)} familyName:${q(s)}`));
  }
}
return (urls.length ? urls : ['']).map(url => ({ json: { ...merged, url }, pairedItem: { item: 0 } }));
