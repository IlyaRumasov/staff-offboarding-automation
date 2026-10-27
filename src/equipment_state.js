// ===== Стан техніки з коментарів заявки: спільний код флоу offboarding, збірка вставляє його замість рядка «// @@equipment». =====
// Вирішує останній коментар про техніку: людини з IT або флоу перевірки техніки («Перевірка техніки (GLPI): ...»).
// Звіти самого offboarding («Автоматичний offboarding») не рахуємо: старий бот писав там «Заборгованості немає».
// \p{L} з прапорцем u: без нього \w і \b у JS не бачать кирилицю.
const EQ_OK = /забор\p{L}*\s+по\s+техн\p{L}*\s+нема|техн\p{L}*\s+(повернуто|повернув|повернула|здано|здав|здала)|нічого\s+не\s+числиться/iu;
const EQ_DEBT = /(закріплен\p{L}*|числиться|не\s+поверну\p{L}*|не\s+здан\p{L}*)[^\r\n]{0,40}(ноут|техн|монітор|комп|пк|телефон|гарнітур|інв)/iu;
const EQ_GLPI = /^\s*Перевірка\s+техніки\s+\(GLPI\)/iu;  // коментар флоу перевірки техніки без висновку = «невідомо»
function equipmentState(journals) {
  let equipment = 'unknown', equipment_note = '';
  for (const j of journals || []) {
    if (!j || !j.notes || /Автоматичний\s+offboarding/i.test(j.notes)) continue;
    if (EQ_DEBT.test(j.notes)) { equipment = 'debt'; equipment_note = j.notes.trim(); }
    else if (EQ_OK.test(j.notes)) { equipment = 'ok'; equipment_note = j.notes.trim(); }
    else if (EQ_GLPI.test(j.notes)) { equipment = 'unknown'; equipment_note = j.notes.trim(); }
  }
  return { equipment, equipment_note };
}
// ===== кінець стану техніки =====
