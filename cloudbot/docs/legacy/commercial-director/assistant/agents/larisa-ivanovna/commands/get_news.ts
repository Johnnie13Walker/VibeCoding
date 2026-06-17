import { LARISA_COMMAND_ALIASES } from "../config";
import { runNewsWorkflow, type NewsWorkflowDeps } from "../workflows/news.workflow";

export function createGetNewsCommand(deps: NewsWorkflowDeps) {
  return {
    name: "get_news",
    aliases: LARISA_COMMAND_ALIASES.getNews,
    async execute(input: { dateMsk: string; topics?: string[] }) {
      const result = await runNewsWorkflow(input, deps);

      return {
        text: result.text,
        payload: result,
      };
    },
  };
}
