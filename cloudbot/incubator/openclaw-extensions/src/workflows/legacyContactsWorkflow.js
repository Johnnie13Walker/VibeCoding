import { handleTelegramText } from '../../contacts/service.js';

const legacyContactsWorkflow = {
  async run(input, context = {}) {
    const result = await handleTelegramText(input.metadata?.message, context);
    if (!result?.handled || !result.reply) return null;
    return {
      response: { text: String(result.reply) },
      nextState: null,
    };
  },

  async continue(_state, input, context = {}) {
    return this.run(input, context);
  },
};

async function runLegacyContactsWorkflow(input, context = {}) {
  const result = await handleTelegramText(input.metadata?.message, context);
  return result;
}

export { legacyContactsWorkflow, runLegacyContactsWorkflow };
