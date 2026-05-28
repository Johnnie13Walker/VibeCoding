import { LARISA_COMMAND_ALIASES, larisaIvanovnaConfig } from "../config";
import { runSearchWorkflow, type SearchWorkflowDeps } from "../workflows/search.workflow";

export function createSearchCommand(deps: SearchWorkflowDeps) {
  return {
    name: "search",
    aliases: [
      ...LARISA_COMMAND_ALIASES.search,
      ...larisaIvanovnaConfig.legacyCommandAliases.search,
    ],
    async execute(input: { query: string }) {
      const result = await runSearchWorkflow(input, deps);

      return {
        text: result.text,
        payload: result,
      };
    },
  };
}
