// Що робити з акаунтом в AD за результатом пошуку (по всьому домену).
// lookup = login: пошук за sAMAccountName; lookup = name: за прізвищем, далі звіряємо ім'я (логіна в заявці немає).
// ad_status: disable | already_done | not_found | multiple | outside_scope | fired_but_enabled | name_not_found | name_multiple
const SCOPE = ',OU=AllUsers,OU=COMPANY,DC=example,DC=com';
const FIRED_OU = 'OU=Уволенные,DC=example,DC=com';
const ACCOUNTDISABLE = 2;

const leaver = $('Loop Over Tickets').first().json;
const one = v => Array.isArray(v) ? v[0] : v;
const low = v => String(one(v) || '').toLowerCase();
const endsWithCI = (s, tail) => s.toLowerCase().endsWith(tail.toLowerCase());
let found = $input.all().map(i => i.json).filter(j => j && j.dn);

const where = j => {
  const dn = String(j.dn);
  const uac = parseInt(one(j.userAccountControl), 10) || 0;
  const ou = endsWithCI(dn, ',' + FIRED_OU) ? 'Уволенные' : (dn.match(/,OU=([^,]+)/) || [])[1] || '?';
  return `${one(j.sAMAccountName)} (${ou}, ${(uac & ACCOUNTDISABLE) ? 'заблокований' : 'активний'})`;
};

let out = { ...leaver, ad_status: '', dn: '', target_dn: '', new_uac: '', ad_matches: 0, candidates: '', found_by_name: false, ignored_disabled: '', skipped_tenure: '', tenure_checked: '' };

if (leaver.lookup === 'name') {
  const pairs = leaver.pairs || [[leaver.gn, leaver.sn]];
  const sns = new Set(pairs.map(p => p[1].toLowerCase()));
  const sameSurname = found.filter(j => sns.has(low(j.sn)));
  const byName = found.filter(j => pairs.some(([g, s]) => low(j.givenName) === g.toLowerCase() && low(j.sn) === s.toLowerCase()));
  // Запасний шлях: акаунт із логіном за шаблоном, у якого ім'я/прізвище порожні або збігаються.
  const byLogin = found.filter(j => (leaver.login_variants || []).includes(low(j.sAMAccountName)) &&
    pairs.some(([g, s]) => (!low(j.givenName) || low(j.givenName) === g.toLowerCase()) && (!low(j.sn) || low(j.sn) === s.toLowerCase())));
  let pick = byName.length ? byName : byLogin;
  // Перевірка за датою створення: дата створення акаунта + «Загалом днів співпраці» із заявки = дата звільнення (допуск 3 дні).
  // Так відсіюються однофамільці й старі дублікати (на реальних заявках збіг був рівно 0 днів, дублікати розходились на 30+).
  const createdOf = j => { const m = String(one(j.whenCreated) || '').match(/^(\d{4})(\d{2})(\d{2})/); return m ? `${m[1]}-${m[2]}-${m[3]}` : ''; };
  const fits = j => { const c = createdOf(j); return !!c && Math.abs(Math.round((Date.parse(leaver.leaver_date) - Date.parse(c)) / 86400000) - leaver.tenure_days) <= 3; };
  const withDate = j => `${where(j)}, створено ${createdOf(j) || '?'}`;
  let tenureMismatch = false;
  if (leaver.tenure_days != null && pick.length) {
    const fit = pick.filter(fits);
    if (fit.length === 0) { tenureMismatch = true; out.candidates = pick.map(withDate).join('; '); }
    else if (fit.length === 1) {
      out.skipped_tenure = pick.filter(j => j !== fit[0]).map(withDate).join('; ');
      out.tenure_checked = `створено ${createdOf(fit[0])}, співпраця ${leaver.tenure_days} дн., звільнення ${leaver.leaver_date}`;
      pick = fit;
    } else { out.candidates = fit.map(withDate).join('; '); pick = fit; }
  } else {
    // Терміну співпраці немає: кілька акаунтів з таким іменем, уже заблоковані дублікати ігноруємо, якщо активний рівно один.
    const active = pick.filter(j => !((parseInt(one(j.userAccountControl), 10) || 0) & ACCOUNTDISABLE));
    if (pick.length > 1 && active.length === 1) {
      out.ignored_disabled = pick.filter(j => j !== active[0]).map(where).join('; ');
      pick = active;
    }
  }
  found = pick;
  out.found_by_login_pattern = !byName.length && found.length === 1;
  if (tenureMismatch) {
    out.ad_status = 'name_tenure_mismatch';
    found = [];
  } else if (found.length === 0) {
    out.ad_status = 'name_not_found';
    out.candidates = sameSurname.slice(0, 5).map(j => `${one(j.displayName) || one(j.cn)}: ${where(j)}`).join('; ');
  } else if (found.length > 1) {
    out.ad_status = 'name_multiple';
    out.candidates = out.candidates || found.map(where).join('; ');
  } else {
    out.login = String(one(found[0].sAMAccountName));
    out.guest_email = `${out.login}_example.com@tenant.example.org.guest.google`;
    out.found_by_name = true;
    out.gn = String(one(found[0].givenName) || leaver.gn);  // як записано в AD
    out.sn = String(one(found[0].sn) || leaver.sn);
  }
}

out.ad_matches = found.length;
if (!out.ad_status) {
  if (found.length === 0) out.ad_status = 'not_found';
  else if (found.length > 1) { out.ad_status = 'multiple'; out.candidates = found.map(where).join('; '); }
  else {
    const dn = String(found[0].dn);
    const uac = parseInt(one(found[0].userAccountControl), 10) || 0;
    const disabled = (uac & ACCOUNTDISABLE) === ACCOUNTDISABLE;
    out.dn = dn;
    if (endsWithCI(dn, ',' + FIRED_OU)) {
      out.ad_status = disabled ? 'already_done' : 'fired_but_enabled';
    } else if (endsWithCI(dn, SCOPE)) {
      // RDN до першої неекранованої коми (CN=Petrenko\, Ivan,OU=...).
      const rdn = dn.match(/^((?:\\.|[^,\\])+),/)[1];
      out.ad_status = 'disable';
      out.new_uac = String(uac | ACCOUNTDISABLE);  // інші прапорці акаунта не чіпаємо
      out.target_dn = `${rdn},${FIRED_OU}`;
    } else {
      out.ad_status = 'outside_scope';
    }
  }
}

return [{ json: out, pairedItem: { item: 0 } }];
