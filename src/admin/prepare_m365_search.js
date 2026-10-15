// Результат передачі диска (запуск або пропуск) + запит пошуку в Microsoft Graph:
// члени тенанта (не гості #EXT#) з таким ім'ям і прізвищем, обидва порядки.
const ctx = $('Code: Decide Drive Action').first().json;
const r = $input.first().json;
const drive = { ...ctx.drive };
if (drive.action === 'transfer') {
  const code = Number(r.statusCode);
  if (code >= 200 && code < 300) { drive.result = 'transferred'; drive.transfer_status = (r.body && r.body.overallTransferStatusCode) || ''; }
  else { drive.result = 'error'; drive.error = `${code || 'немає відповіді'}: ${(r.body && r.body.error && r.body.error.message) || (r.error && r.error.message) || 'перенесення не запущено'}`; }
} else drive.result = drive.status;
const e = s => String(s).replace(/'/g, "''");
const filter = ctx.pairs.map(([g, s]) => `(givenName eq '${e(g)}' and surname eq '${e(s)}')`).join(' or ');
return [{ json: { ...ctx, drive,
  url: 'https://graph.microsoft.com/v1.0/users?$select=id,userPrincipalName,mail,givenName,surname,accountEnabled,userType&$top=10&$filter=' + encodeURIComponent(filter) },
  pairedItem: { item: 0 } }];
