// Що робити з диском: drive.action = transfer | ask | none | skip
const ctx = $('Code: Prepare Drive Transfer').first().json;
const d = { ...(ctx.drive || {}) };
const res = $input.all().map(i => i.json).filter(r => r.statusCode !== undefined);
const users = {};
for (const r of res) {
  if (Number(r.statusCode) !== 200 || !r.body) continue;
  for (const u of (r.body.users || (r.body.primaryEmail ? [r.body] : []))) if (!u.suspended) users[u.id] = u;
}
const list = Object.values(users);
const leaverOk = ['suspended', 'already_suspended'].includes(ctx.google.result);
d.candidates = list.map(u => `${(u.name && u.name.fullName) || ''} (${u.primaryEmail})`).join('; ');

if (ctx.drive_done_before) { d.action = 'skip'; d.status = 'done_before'; }
else if (d.mode === 'none') { d.action = 'none'; d.status = 'not_needed'; }
else if (d.mode === 'unknown') { d.action = 'none'; d.status = 'unknown_target'; }
else if (!leaverOk) { d.action = 'none'; d.status = 'no_leaver_account'; }
else if (list.length === 0) { d.action = 'none'; d.status = d.mode === 'email' ? 'recipient_not_found' : 'recipient_name_not_found'; }
else if (list.length > 1) { d.action = 'none'; d.status = 'recipient_multiple'; }
else {
  const u = list[0];
  d.recipient_id = u.id; d.recipient_email = u.primaryEmail.toLowerCase();
  d.recipient_name = (u.name && u.name.fullName) || u.primaryEmail;
  const confirmed = d.mode === 'email' || (ctx.confirmed_email && ctx.confirmed_email === d.recipient_email);
  if (confirmed) { d.action = 'transfer'; d.status = 'transfer'; }
  else { d.action = 'ask'; d.status = 'ask'; }
}
return [{ json: { ...ctx, drive: d }, pairedItem: { item: 0 } }];
