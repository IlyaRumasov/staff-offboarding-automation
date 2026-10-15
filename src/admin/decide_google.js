// Що робити з акаунтом Google: google.status = suspend | already_suspended | not_found | multiple | error
const ctx = $('Code: Prepare Google Search').first().json;
const res = $input.all().map(i => i.json);
const err = res.find(r => Number(r.statusCode) !== 200);
const users = {};
for (const r of res) for (const u of ((r.body && r.body.users) || [])) users[u.id] = u;
const list = Object.values(users);
const google = { status: '', id: '', email: '', candidates: list.map(u => `${u.primaryEmail}${u.suspended ? ' (призупинений)' : ''}`).join('; ') };
if (err && !list.length) { google.status = 'error'; google.error = `${err.statusCode}: ${(err.body && err.body.error && err.body.error.message) || err.statusMessage || 'немає відповіді'}`; }
else if (list.length === 0) google.status = 'not_found';
else if (list.length > 1) google.status = 'multiple';
else {
  const u = list[0];
  google.id = u.id; google.email = u.primaryEmail;
  google.status = u.suspended ? 'already_suspended' : 'suspend';
}
return [{ json: { ...ctx, google }, pairedItem: { item: 0 } }];
