// Розбір заявок «Admin | Leaver» (трекер 25): дата звільнення, ім'я (обидва порядки), кому передати диск.
// Вихід: action = 'process' або 'notify' (бракує даних; коментар пишеться один раз, пам'ять у static data).
const TERM_DATE_CF_ID = 30;   // «Termination date» (на тесті інший номер, тому шукаємо й за назвою)
const ENG_CF_ID = 11, UKR_CF_ID = 103, MANAGER_CF_ID = 25;

const state = $getWorkflowStaticData('global');
state.notified = state.notified || {};
const today = DateTime.now().setZone('Europe/Kyiv').toISODate();

let issues = [];
for (const it of $input.all()) {
  if (Array.isArray(it.json.issues)) issues.push(...it.json.issues);
  else if (it.json && it.json.id) issues.push(it.json);
}
const cf = (issue, id, name) => (issue.custom_fields || []).find(f => f.id === id || f.name === name);
const cfv = (issue, id, name) => { const f = cf(issue, id, name); return f && f.value ? String(f.value).trim() : ''; };

// Транслітерація КМУ-2010 (як імена записані в AD/Google).
const TR = { а:'a', б:'b', в:'v', г:'h', ґ:'g', д:'d', е:'e', є:'ie', ж:'zh', з:'z', и:'y', і:'i', ї:'i', й:'i', к:'k', л:'l',
  м:'m', н:'n', о:'o', п:'p', р:'r', с:'s', т:'t', у:'u', ф:'f', х:'kh', ц:'ts', ч:'ch', ш:'sh', щ:'shch', ь:'', ю:'iu', я:'ia',
  ы:'y', э:'e', ё:'io', ъ:'' };
const TR_START = { є:'ye', ї:'yi', й:'y', ю:'yu', я:'ya', ё:'yo' };
function translit(word) {
  const w = word.toLowerCase().replace(/[’'ʼ`]/g, '').replace(/зг/g, 'zgh');
  let out = '';
  for (let i = 0; i < w.length; i++) out += (i === 0 && TR_START[w[i]]) || (TR[w[i]] !== undefined ? TR[w[i]] : w[i]);
  return out.charAt(0).toUpperCase() + out.slice(1);
}
const isCyr = s => /[А-Яа-яЁёЄєІіЇїҐґ]/.test(s);
const isLat = s => /^[A-Za-z][A-Za-z'’ʼ-]*$/.test(s);

// Пари [ім'я, прізвище] в обох порядках: «Ivan Testovenko» і «Probenko Olha» пишуть по-різному.
function namePairs(raw) {
  const parts = String(raw || '').replace(/^(ФОП|ФЛП)\s+/i, '').split(/[\s/,]+/).filter(Boolean);
  if (parts.length < 2) return [];
  let a = parts[0], b = parts[1];
  if (isCyr(a) || isCyr(b)) { if (!isCyr(a) || !isCyr(b)) return []; a = translit(a); b = translit(b); }
  else if (!isLat(a) || !isLat(b)) return [];
  const pairs = [[a, b], [b, a]];
  return pairs.filter((p, i) => i === 0 || p[0] !== pairs[0][0]);
}

function parseDate(issue) {
  let d = cfv(issue, TERM_DATE_CF_ID, 'Termination date') || issue.due_date || '';
  d = String(d).trim();
  if (!d) return { reason: 'no_date' };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || !DateTime.fromISO(d).isValid) return { reason: 'bad_date', value: d };
  return { date: d };
}

// Кому передати диск. mode: email | name | manager | none
const NO_TRANSFER = /(не\s*(потрібно|треба|переадресов\p{L}*|передава\p{L}*)|видалити|немає|^ні$|^-$)/iu;
function parseDrive(description, manager) {
  const d = description || '';
  if (/(дані|диск)[^\r\n]{0,40}передавати\s+не\s+потрібно/i.test(d)) return { mode: 'none', text: 'передавати не потрібно' };
  const m = d.match(/Переадресація\s+диску\s*[:\-–—]\s*([^\r\n]*)/i)
         || d.match(/Дані\s+(?:пошти\s+(?:та|і|й)\s+)?диску\s+передати\s*[:\-–—]?\s*([^\r\n]*)/i);
  if (m) {
    const v = m[1].trim();
    const email = (v.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/) || [])[0];
    if (email) return { mode: 'email', email: email.toLowerCase(), text: v };
    if (!v || NO_TRANSFER.test(v)) return { mode: 'none', text: v || 'не вказано' };
    const pairs = namePairs(v.replace(/[-–—].*$/, '').trim());
    return pairs.length ? { mode: 'name', name: v, pairs, text: v } : { mode: 'unknown', text: v };
  }
  const mp = namePairs(manager);
  return mp.length ? { mode: 'manager', name: manager, pairs: mp, text: `не вказано, менеджер: ${manager}` }
                   : { mode: 'unknown', text: 'не вказано, менеджера в заявці немає' };
}

const NOTES = {
  no_date: () => ['• Поле «Termination date»: порожнє.\n• Due date: порожня.',
    'не вказано дату звільнення, тому невідомо, коли закривати доступи.',
    ['заповніть «Termination date» (РРРР-ММ-ДД); у день звільнення або пізніше автоматизація обробить заявку сама.']],
  bad_date: v => [`• Дата звільнення в заявці: «${v}».`, `дату «${v}» не вдалося розпізнати (очікується РРРР-ММ-ДД).`,
    ['виправте дату в полі «Termination date», і автоматизація обробить заявку сама.']],
  no_name: v => [`• «Contractor (ENG)»: «${v.eng || ''}».\n• «Contractor (UKR)»: «${v.ukr || ''}».`,
    'не вдалося визначити ім\'я та прізвище працівника, тому шукати його в AD, Google і M365 немає за чим.',
    ['заповніть «Contractor (ENG)» у форматі «Ім\'я Прізвище» латиницею.']],
};
const fmt = ([checked, result, next]) =>
  `⚠ Автоматичний offboarding не виконано.\n\nЩо перевірено:\n${checked}\n\nРезультат: ${result}\n\n` +
  `Що робити далі:\n${next.map((s, i) => `${i + 1}. ${s.charAt(0).toUpperCase()}${s.slice(1)}`).join('\n')}\n\n` +
  'Заявку залишено відкритою. Нічого в AD, Google і M365 не змінено. Автоматизація перевіряє заявку щодня о 18:00; про ту саму проблему повторно не пише.';

const results = [];
const openIds = new Set();
for (const issue of issues) {
  if (!issue || !issue.tracker || issue.tracker.id !== 25) continue;
  const id = issue.id;
  openIds.add(String(id));
  const D = parseDate(issue);
  if (D.date && D.date > today) continue;  // ще не звільнився

  const eng = cfv(issue, ENG_CF_ID, 'Contractor (ENG)');
  const ukr = cfv(issue, UKR_CF_ID, 'Contractor (UKR)');
  const pairs = namePairs(eng).length ? namePairs(eng) : namePairs(ukr);
  const problem = D.reason ? D : (!pairs.length ? { reason: 'no_name', value: { eng, ukr } } : null);
  if (problem) {
    const key = 'input:' + problem.reason + ':' + JSON.stringify(problem.value || '');
    if (state.notified[id] === key) continue;
    state.notified[id] = key;
    results.push({ json: { action: 'notify', id, reason: problem.reason, note: fmt(NOTES[problem.reason](problem.value)) } });
    continue;
  }
  if (String(state.notified[id] || '').startsWith('input:')) delete state.notified[id];
  const manager = cfv(issue, MANAGER_CF_ID, 'Manager');
  // Шаблони логінів в AD (запасний пошук, якщо в акаунта не заповнені ім'я/прізвище):
// ім'я.прізвище, і.прізвище, ms.і.прізвище, ms.ім'я.прізвище (ms. у старих акаунтів).
const loginVariants = (g, s) => {
  const G = g.toLowerCase().replace(/[^a-z-]/g, ''), S = s.toLowerCase().replace(/[^a-z-]/g, '');
  if (!G || !S) return [];
  return [`${G}.${S}`, `${G[0]}.${S}`, `ms.${G[0]}.${S}`, `ms.${G}.${S}`];
};
  const ldapEsc = s => s.replace(/[\\*()\0]/g, c => '\\' + c.charCodeAt(0).toString(16).padStart(2, '0'));
  results.push({ json: {
    action: 'process', id, subject: issue.subject || '', leaver_date: D.date,
    person: eng || ukr, pairs, drive: parseDrive(issue.description, manager === '-' ? '' : manager),
    login_variants: [...new Set(pairs.flatMap(([g, s]) => loginVariants(g, s)))],
    ldap_filter: '(&(objectClass=user)(|' + pairs.map(([g, s]) => `(&(givenName=${ldapEsc(g)})(sn=${ldapEsc(s)}))`).join('') +
      [...new Set(pairs.flatMap(([g, s]) => loginVariants(g, s)))].map(v => `(sAMAccountName=${ldapEsc(v)})`).join('') + '))',
  } });
}
for (const k of Object.keys(state.notified)) if (!openIds.has(k)) delete state.notified[k];
return results;
