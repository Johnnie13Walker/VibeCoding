import { LARISA_COMMAND_ALIASES, larisaIvanovnaConfig } from "../config";
import type { GetDayBriefInput } from "../schemas/brief.schema";
import { normalizeDayBriefRequest } from "./get_day_brief";
import { runPlanDayWorkflow } from "../workflows/plan_day.workflow";
import type { DailyBriefWorkflowDeps } from "../workflows/daily_brief.workflow";

export function createPlanDayCommand(deps: DailyBriefWorkflowDeps) {
  return {
    name: "plan_day",
    aliases: [
      ...LARISA_COMMAND_ALIASES.planDay,
      ...larisaIvanovnaConfig.legacyCommandAliases.planDay,
    ],
    async execute(input: GetDayBriefInput = {}) {
      const result = await runPlanDayWorkflow(normalizeDayBriefRequest(input), deps);

      return {
        text: result.text,
        payload: result,
      };
    },
  };
}
