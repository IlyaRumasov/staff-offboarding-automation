// Відкриті заявки на звільнення (трекер 25 «Admin | Leaver» і 41 «GA | Leaver»): хто працівник і запити пошуку в GLPI.
// Адмін: ім'я з полів «Contractor (ENG)» і «Contractor (UKR)». Лінійний: логін з рядка «AD -» (або поля «AD login») і ПІБ з рядка «ГА -» чи теми.
// Заявки, де немає ні логіна, ні імені, пропускаємо: шукати в GLPI нема за чим.
// @@glpi
const TRACKERS = { 25: 'admin', 41: 'linear' };
const ENG_CF_ID = 11, UKR_CF_ID = 103, LOGIN_CF_ID = 87;
const LOGIN_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

// Транслітерація за постановою КМУ №55 (2010), як імена записані латиницею в GLPI й AD (Зразковий Олег -> Zrazkovyi Oleh).
const TR = { а:'a', б:'b', в:'v', г:'h', ґ:'g', д:'d', е:'e', є:'ie', ж:'zh', з:'z', и:'y', і:'i', ї:'i', й:'i', к:'k', л:'l',
  м:'m', н:'n', о:'o', п:'p', р:'r', с:'s', т:'t', у:'u', ф:'f', х:'kh', ц:'ts', ч:'ch', ш:'sh', щ:'shch', ь:'', ю:'iu', я:'ia',
  ы:'y', э:'e', ё:'io', ъ:'' };
const TR_START = { є:'ye', ї:'yi', й:'y', ю:'yu', я:'ya', ё:'yo' };
function translit(word) {
  const w = word.toLowerCase().replace(/[’'ʼ`]/g, '').replace(/зг/g, 'zgh');
  let out = '';
  for (let i = 0; i < w.length; i++) out += (i === 0 && TR_START[w[i]]) || (TR[w[i]] !== undefined ? TR[w[i]] : w[i]);
  return out;
}
const isCyr = w => /^[А-Яа-яЁёЄєІіЇїҐґ’'ʼ-]+$/.test(w);
// Латинські пари з кириличного імені (обидва порядки); латинські імена glpiPairs розбирає сам.
const latinPairs = name => {
  const w = String(name || '').replace(/^(ФОП|ФЛП)\s+/i, '').split(/\s+/).filter(Boolean);
  if (w.length < 2 || !isCyr(w[0]) || !isCyr(w[1])) return [];
  const [a, b] = [translit(w[0]), translit(w[1])];
  return [[a, b], [b, a]];
};
const cf = (issue, id, name) => {
  const f = (issue.custom_fields || []).find(x => x.id === id || x.name === name);
  return f && f.value ? String(f.value).trim() : '';
};

let issues = [];
for (const it of $input.all()) {
  if (Array.isArray(it.json.issues)) issues.push(...it.json.issues);
  else if (it.json && it.json.id) issues.push(it.json);
}

// Виклик з агента (перед «обробити зараз»): перевіряємо лише цю заявку
const ONLY = (() => { try { return $('When Called by Agent').isExecuted ? (String($('When Called by Agent').first().json.ticket_id || '') || null) : null; } catch (e) { return null; } })();
if (ONLY) issues = issues.filter(i => String(i.id) === ONLY);

const out = [];
for (const issue of issues) {
  const kind = issue && issue.tracker && TRACKERS[issue.tracker.id];
  if (!kind) continue;
  let login = '', names = [];
  if (kind === 'admin') names = [cf(issue, ENG_CF_ID, 'Contractor (ENG)'), cf(issue, UKR_CF_ID, 'Contractor (UKR)')];
  else {
    // [ \t]* замість \s*, щоб не перескочити на наступний рядок, коли поле порожнє.
    const m = (issue.description || '').match(/(?:^|[\s|])AD[ \t]*[-–—:][ \t]*([^\r\n]*)/i);
    const raw = ((m && m[1].trim()) || cf(issue, LOGIN_CF_ID, 'AD login')).split(/[\s@]+/)[0];
    if (LOGIN_RE.test(raw)) login = raw.toLowerCase();
    const g = (issue.description || '').match(/(?:^|[\s|])ГА[ \t]*[-–—:][ \t]*([^\r\n]*)/);
    names = [((g && g[1]) || (issue.subject || '').split('|')[2] || '').trim()];
  }
  names = names.filter(n => n && n !== '-');
  const pairs = names.flatMap(latinPairs);
  const urls = glpiUrls(login, names, pairs);
  if (!urls.user_url && !urls.assets_url) continue;
  out.push({ json: { id: issue.id, kind, subject: issue.subject || '', login, names, pairs, ...urls } });
}
return out;
