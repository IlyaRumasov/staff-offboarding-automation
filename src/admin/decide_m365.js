// Що робити з акаунтом M365: m365.status = delete | not_found | multiple | error
const ctx = $('Code: Prepare M365 Search').first().json;
const r = $input.first().json;
const m365 = { status: '', id: '', upn: '' };
if (Number(r.statusCode) !== 200) {
  m365.status = 'error';
  m365.error = `${r.statusCode || 'немає відповіді'}: ${(r.body && r.body.error && r.body.error.message) || 'пошук не вдався'}`;
} else {
  const list = ((r.body && r.body.value) || []).filter(u => u.userType !== 'Guest' && !String(u.userPrincipalName).includes('#EXT#'));
  m365.candidates = list.map(u => u.userPrincipalName).join('; ');
  if (list.length === 0) m365.status = 'not_found';
  else if (list.length > 1) m365.status = 'multiple';
  else { m365.status = 'delete'; m365.id = list[0].id; m365.upn = list[0].userPrincipalName; }
}
return [{ json: { ...ctx, m365 }, pairedItem: { item: 0 } }];
