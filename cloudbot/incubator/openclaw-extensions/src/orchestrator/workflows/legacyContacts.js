import { handleTelegramText } from '../../../contacts/service.js';

export async function runLegacyContactsWorkflow(input, ctx = {}) {
  // Временная совместимость: legacy-модуль принимает исходный telegram message.
  return handleTelegramText(input.metadata?.message, ctx);
}

