import { collectDiagnostics, formatDiagnosticsMessage } from '../services/diagnostics.js';

const diagnosticsWorkflow = {
  async run(_input, context = {}) {
    const diag = await collectDiagnostics(context);
    return {
      response: { text: formatDiagnosticsMessage(diag) },
      nextState: null,
    };
  },

  async continue(_state, input, context = {}) {
    return this.run(input, context);
  },
};

async function runDiagnosticsWorkflow(input, context = {}) {
  const out = await diagnosticsWorkflow.run(input, context);
  return { handled: true, reply: out.response.text };
}

export { diagnosticsWorkflow, runDiagnosticsWorkflow };
