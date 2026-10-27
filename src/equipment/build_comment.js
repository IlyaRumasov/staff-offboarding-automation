// Результат перевірки GLPI -> коментар у заявку «Перевірка техніки (GLPI): ...». Флоу offboarding читають саме цей коментар:
// «числиться техніка» = борг (заявку не закривають), «Заборгованості по техніці немає» = техніку перевірено, інше = потрібна перевірка IT.
// «Немає» пишемо, коли людина є в GLPI і за нею нічого не числиться. Людини в GLPI немає: адмін = перевірка IT,
// лінійний = теж «немає» (лінійні працюють на своїй техніці й у GLPI їх зазвичай немає; рішення користувача 27.10.2026).
// Пишемо лише коли висновок змінився (порівнюємо з останнім таким коментарем). Якщо останнє слово про техніку за людиною
// (IT написав «закріплений ноутбук» чи «заборгованості немає»), мовчимо: рішення вже прийняте людиною.
// @@glpi
const ctx = $('Loop Over Tickets').first().json;
const t = $('[Redmine] Get Ticket History').first().json;
const journals = ((t.issue || t).journals || []).filter(j => j && j.notes);
const MARK = 'Перевірка техніки (GLPI):';
const isOurs = n => n.trim().startsWith(MARK);
const isOffboarding = n => /Автоматичний\s+offboarding/i.test(n);
// Ті самі ознаки, що в src/equipment_state.js (флоу offboarding).
const EQ_OK = /забор\p{L}*\s+по\s+техн\p{L}*\s+нема|техн\p{L}*\s+(повернуто|повернув|повернула|здано|здав|здала)|нічого\s+не\s+числиться/iu;
const EQ_DEBT = /(закріплен\p{L}*|числиться|не\s+поверну\p{L}*|не\s+здан\p{L}*)[^\r\n]{0,40}(ноут|техн|монітор|комп|пк|телефон|гарнітур|інв)/iu;
const last = journals.filter(j => isOurs(j.notes) || (!isOffboarding(j.notes) && (EQ_OK.test(j.notes) || EQ_DEBT.test(j.notes)))).pop();
const humanDecided = !!last && !isOurs(last.notes);

const g = glpiCheck(ctx.login, ctx.names, ctx.pairs, $('[GLPI] Open Session').first().json, $('[GLPI] Find User').first().json,
  $input.first().json);
const who = ctx.login || ctx.names[0] || '';
const list = xs => xs.map(x => `– ${x}`).join('\n');
const contact = g.possible.length ? `\nУ полі «Контакт» GLPI згадується «${who}» (перевірте, чи це техніка працівника):\n${list(g.possible)}` : '';
const it = 'Потрібна перевірка IT: перевірте техніку вручну і напишіть результат коментарем.';
const TEXT = {
  assigned: () => `${MARK} за працівником числиться техніка.\nУ GLPI на користувачі ${g.glpi_login}:\n${list(g.items)}` +
    (g.more ? `\n… і ще ${g.more}` : '') + contact + '\nПісля повернення зніміть техніку з користувача в GLPI: ця перевірка напише про це сама.',
  clear: () => `${MARK} Заборгованості по техніці немає.`,
  check: () => `${MARK} потрібна перевірка IT.\nКористувач ${g.glpi_login} є в GLPI, позицій на ньому немає.${contact}\n${it}`,
  not_in_glpi: () => `${MARK} потрібна перевірка IT.\nПрацівника «${who}» у GLPI не знайдено (ні за логіном, ні за ім'ям і прізвищем).${contact}\n${it}`,
  ambiguous: () => `${MARK} потрібна перевірка IT.\nУ GLPI під «${who}» підходять кілька користувачів: ${g.glpi_login}.\n${it}`,
  error: () => `${MARK} перевірити GLPI не вдалося (${g.error}). Перевірка повториться щогодини.`,
};
const linearNone = ctx.kind === 'linear' && g.status === 'not_in_glpi' && !g.possible.length;
const note = linearNone ? TEXT.clear() : TEXT[g.status]();
const prev = journals.filter(j => isOurs(j.notes)).pop();
// Помилку GLPI для лінійних не пишемо: вона не має скасувати попередній висновок «числиться техніка» (наступна перевірка за годину).
const quiet = ctx.kind === 'linear' && g.status === 'error';
const notify = !humanDecided && !quiet && (!prev || prev.notes.trim() !== note.trim());
return [{ json: { id: ctx.id, kind: ctx.kind, status: g.status, items: g.items.length, human_decided: humanDecided, notify, note },
  pairedItem: { item: 0 } }];
