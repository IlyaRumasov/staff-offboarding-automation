// ===== GLPI (облік техніки): пошук людини і її техніки. Збірка вставляє цей код у Code-ноди замість рядка «// @@glpi». =====
// Хто людина в GLPI: користувач, у якого логін = логін AD, або прізвище й ім'я з заявки (латиницею чи кирилицею, обидва порядки).
// Техніка людини: позиції, де поле «Користувач» = цей користувач. Поле «Контакт» (вільний текст: логін@ПК або ПІБ)
// лише підказка: такі позиції показуємо як «можливо», але самі по собі вони нічого не підтверджують.
// Пошук GLPI за «містить» знаходить і схожі логіни (a.ivanov -> a.ivanova), тому точний збіг перевіряємо тут.
const GLPI_URL = '<GLPI_URL>/apirest.php';
const glpiNorm = s => String(s || '').replace(/<[^>]*>/g, '').replace(/[’ʼ`]/g, "'").replace(/\s+/g, ' ').trim().toLowerCase();

// Пари [ім'я, прізвище] для пошуку: з готових латинських пар і з сирих рядків заявки (обидва порядки; для 3+ слів ще перше+останнє).
function glpiPairs(names, pairs) {
  const out = [];
  const add = (g, s) => { g = glpiNorm(g); s = glpiNorm(s); if (g && s && !out.some(p => p[0] === g && p[1] === s)) out.push([g, s]); };
  for (const [g, s] of pairs || []) add(g, s);
  for (const raw of names || []) {
    const w = String(raw || '').replace(/^(ФОП|ФЛП)\s+/i, '').split(/[\s\/|,]+/).filter(x => /^[\p{L}'’ʼ-]{2,}$/u.test(x));
    if (w.length < 2) continue;
    add(w[0], w[1]); add(w[1], w[0]);
    if (w.length >= 3) { add(w[0], w[w.length - 1]); add(w[w.length - 1], w[0]); }
  }
  return out.slice(0, 8);
}

// Два запити: користувачі GLPI (логін або прізвище+ім'я) і техніка (поле «Користувач» або «Контакт» містить логін чи слово з ПІБ).
function glpiUrls(login, names, pairs) {
  const P = glpiPairs(names, pairs), e = encodeURIComponent;
  const c = [];
  const crit = (i, f, v, link) => (link ? `&criteria[${i}][link]=${link}` : '') +
    `&criteria[${i}][field]=${f}&criteria[${i}][searchtype]=contains&criteria[${i}][value]=${e(v)}`;
  let i = 0;
  if (login) c.push(crit(i++, 1, `^${login}$`));
  for (const [g, s] of P) {
    c.push(`${i ? `&criteria[${i}][link]=OR` : ''}&criteria[${i}][criteria][0][field]=34&criteria[${i}][criteria][0][searchtype]=contains` +
      `&criteria[${i}][criteria][0][value]=${e('^' + s + '$')}&criteria[${i}][criteria][1][link]=AND&criteria[${i}][criteria][1][field]=9` +
      `&criteria[${i}][criteria][1][searchtype]=contains&criteria[${i}][criteria][1][value]=${e('^' + g + '$')}`);
    i++;
  }
  const words = [...new Set([login, ...P.flat()].filter(w => w && w.length >= 3))];
  const a = [];
  let j = 0;
  for (const w of words) { a.push(crit(j, 70, w, j ? 'OR' : '')); j++; a.push(crit(j, 7, w, 'OR')); j++; }
  return {
    user_url: c.length ? `${GLPI_URL}/search/User?${c.join('').slice(1)}&forcedisplay[0]=1&forcedisplay[1]=2&forcedisplay[2]=9&forcedisplay[3]=34&uid_cols=true&range=0-50` : '',
    assets_url: a.length ? `${GLPI_URL}/search/AllAssets?${a.join('').slice(1)}&forcedisplay[0]=1&forcedisplay[1]=5&forcedisplay[2]=6&forcedisplay[3]=7` +
      '&forcedisplay[4]=23&forcedisplay[5]=31&forcedisplay[6]=70&uid_cols=true&range=0-500' : '',
  };
}

// Результат: status = assigned | clear | check | not_in_glpi | ambiguous | error; items (за користувачем), possible (лише «Контакт»).
function glpiCheck(login, names, pairs, session, users, assets) {
  const P = glpiPairs(names, pairs), L = glpiNorm(login);
  const bad = r => !r || Number(r.statusCode) !== 200 || !r.body;
  const why = r => `${(r && r.statusCode) || 'немає відповіді'}${r && r.body ? ': ' + String(JSON.stringify(r.body)).slice(0, 120) : ''}`;
  if (bad(session)) return { status: 'error', error: 'вхід у GLPI ' + why(session), items: [], possible: [] };
  if (bad(users) || bad(assets)) return { status: 'error', error: 'пошук у GLPI ' + why(bad(users) ? users : assets), items: [], possible: [] };
  const val = (r, k) => glpiNorm(r[k]);
  const found = (users.body.data || []).filter(u => (L && val(u, 'User.name') === L) ||
    P.some(([g, s]) => val(u, 'User.realname') === s && val(u, 'User.firstname') === g));
  const logins = [...new Set(found.map(u => val(u, 'User.name')))];
  const TYPES = { Computer: "Комп'ютер", Monitor: 'Монітор', Peripheral: 'Периферія', Printer: 'Принтер', Phone: 'Телефон', NetworkEquipment: 'Мережеве обладнання' };
  const line = r => {
    const f = (k, label) => { const v = String(r[k] || '').replace(/<[^>]*>/g, '').trim(); return v ? `${label}${v}` : ''; };
    return [`${TYPES[r.itemtype] || r.itemtype} «${String(r['AllAssets..name'] || 'без назви').replace(/<[^>]*>/g, '').trim()}»`,
      f('AllAssets..otherserial', 'інв. № '), f('AllAssets..serial', 'сер. № '), f('AllAssets.Manufacturer.name', ''),
      f('AllAssets.State.completename', 'статус: '), f('AllAssets..contact', 'контакт: ')].filter(Boolean).join(', ');
  };
  const rows = assets.body.data || [];
  const owner = r => String(r['AllAssets.User.name'] || '').split('$#$').map(glpiNorm);
  const items = rows.filter(r => owner(r).some(o => logins.includes(o))).map(line);
  const tokens = r => glpiNorm(r['AllAssets..contact']).split(/[\s@\\\/,;()]+/).filter(Boolean);
  const possible = rows.filter(r => !owner(r).some(o => logins.includes(o)))
    .filter(r => { const t = tokens(r); return (L && t.includes(L)) || P.some(([g, s]) => t.includes(g) && t.includes(s)); }).map(line);
  const status = logins.length > 1 ? 'ambiguous' : items.length ? 'assigned' : !logins.length ? 'not_in_glpi' : possible.length ? 'check' : 'clear';
  return { status, glpi_login: logins.join(', '), items: items.slice(0, 20), possible: possible.slice(0, 10), more: Math.max(0, items.length - 20) };
}

// ===== кінець GLPI =====
