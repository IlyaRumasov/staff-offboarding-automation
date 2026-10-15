// Пошук в AD за ім'ям і прізвищем (обидва порядки) по всьому домену. Блокуємо лише при єдиному збігу в OU=AllUsers.
// ad.status: disable | already_done | not_found | multiple | outside_scope | fired_but_enabled
const SCOPE = ',OU=AllUsers,OU=COMPANY,DC=example,DC=com';
const FIRED_OU = 'OU=Уволенные,DC=example,DC=com';
const ctx = $('Loop Over Tickets').first().json;
const one = v => Array.isArray(v) ? v[0] : v;
const endsCI = (s, t) => s.toLowerCase().endsWith(t.toLowerCase());
const low = v => String(one(v) || '').toLowerCase();
const all = $input.all().map(i => i.json).filter(j => j && j.dn);
// Спершу збіг імені й прізвища; якщо нема, запасний шлях: логін за шаблоном, ім'я/прізвище порожні або збігаються.
const byName = all.filter(j => ctx.pairs.some(([g, s]) => low(j.givenName) === g.toLowerCase() && low(j.sn) === s.toLowerCase()));
const byLogin = all.filter(j => (ctx.login_variants || []).includes(low(j.sAMAccountName)) &&
  ctx.pairs.some(([g, s]) => (!low(j.givenName) || low(j.givenName) === g.toLowerCase()) && (!low(j.sn) || low(j.sn) === s.toLowerCase())));
const found = byName.length ? byName : byLogin;
const where = j => {
  const dn = String(j.dn), uac = parseInt(one(j.userAccountControl), 10) || 0;
  const ou = endsCI(dn, ',' + FIRED_OU) ? 'Уволенные' : (dn.match(/,OU=([^,]+)/) || [])[1] || '?';
  return `${one(j.sAMAccountName)} (${ou}, ${(uac & 2) ? 'заблокований' : 'активний'})`;
};
const ad = { status: '', dn: '', target_dn: '', new_uac: '', login: '', candidates: found.map(where).join('; '),
  by_login_pattern: !byName.length && byLogin.length === 1 };
if (found.length === 0) ad.status = 'not_found';
else if (found.length > 1) ad.status = 'multiple';
else {
  const j = found[0], dn = String(j.dn), uac = parseInt(one(j.userAccountControl), 10) || 0;
  ad.dn = dn; ad.login = String(one(j.sAMAccountName) || '');
  if (endsCI(dn, ',' + FIRED_OU)) ad.status = (uac & 2) ? 'already_done' : 'fired_but_enabled';
  else if (endsCI(dn, SCOPE)) {
    ad.status = 'disable';
    ad.new_uac = String(uac | 2);  // лише ACCOUNTDISABLE, інші прапорці не чіпаємо
    ad.target_dn = `${dn.match(/^((?:\\.|[^,\\])+),/)[1]},${FIRED_OU}`;
  } else ad.status = 'outside_scope';
}
return [{ json: { ...ctx, ad }, pairedItem: { item: 0 } }];
