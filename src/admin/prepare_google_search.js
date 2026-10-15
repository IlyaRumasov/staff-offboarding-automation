// Результат кроку AD (блокування і перенесення, або пропуск) + запити пошуку людини в Google.
// По одному запиту на кожен порядок імені: Google не вміє OR у query.
const ctx = $('Code: Decide AD Action').first().json;
const r = $input.first().json;
const text = e => String((e && (e.message || e.description)) || e || 'невідома помилка');
const ad = { ...ctx.ad };
if (ad.status === 'disable') {
  const disableErr = $('[AD] Disable Account').first().json.error;   // блокування не вдалося: перенесення не запускалось
  const err = disableErr || r.error;                                  // інакше помилка могла бути лише в перенесенні
  if (err) { ad.result = 'error'; ad.error = `${disableErr ? 'блокування' : 'перенесення в «Уволенные»'}: ${text(err)}`; }
  else ad.result = 'disabled';
} else ad.result = ad.status;
const merged = { ...ctx, ad };
const q = s => `'${String(s).replace(/'/g, "\\'")}'`;
return ctx.pairs.map(([g, s]) => ({ json: { ...merged,
  url: 'https://admin.googleapis.com/admin/directory/v1/users?customer=my_customer&maxResults=10&query=' +
       encodeURIComponent(`givenName:${q(g)} familyName:${q(s)}`) }, pairedItem: { item: 0 } }));
