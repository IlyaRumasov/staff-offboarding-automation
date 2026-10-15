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

let out = { ...leaver, ad_status: '', dn: '', target_dn: '', new_uac: '', ad_matches: 0, candidates: '', found_by_name: false };

if (leaver.lookup === 'name') {
  const gn = leaver.gn.toLowerCase(), sn = leaver.sn.toLowerCase();
  const sameSurname = found.filter(j => low(j.sn) === sn);
  const byName = found.filter(j => low(j.givenName) === gn && low(j.sn) === sn);
  // Запасний шлях: акаунт із логіном за шаблоном, у якого ім'я/прізвище порожні або збігаються.
  const byLogin = found.filter(j => (leaver.login_variants || []).includes(low(j.sAMAccountName)) &&
    (!low(j.givenName) || low(j.givenName) === gn) && (!low(j.sn) || low(j.sn) === sn));
  found = byName.length ? byName : byLogin;
  out.found_by_login_pattern = !byName.length && byLogin.length === 1;
  if (found.length === 0) {
    out.ad_status = 'name_not_found';
    out.candidates = sameSurname.slice(0, 5).map(j => `${one(j.displayName) || one(j.cn)}: ${where(j)}`).join('; ');
  } else if (found.length > 1) {
    out.ad_status = 'name_multiple';
    out.candidates = found.map(where).join('; ');
  } else {
    out.login = String(one(found[0].sAMAccountName));
    out.guest_email = `${out.login}_example.com@tenant.example.org.guest.google`;
    out.found_by_name = true;
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
