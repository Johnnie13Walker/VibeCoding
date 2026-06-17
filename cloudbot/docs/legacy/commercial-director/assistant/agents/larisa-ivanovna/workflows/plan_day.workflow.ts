import { buildDayBrief, type DailyBriefWorkflowDeps } from "./daily_brief.workflow";
import type { DayBrief, DayBriefRequest } from "../schemas/brief.schema";
import { formatTelegramPlanDay } from "../formatters/telegramPlanDay.formatter";

export interface PlanDayWorkflowResult {
  text: string;
  brief: DayBrief;
}

export async function runPlanDayWorkflow(
  input: DayBriefRequest,
  deps: DailyBriefWorkflowDeps,
): Promise<PlanDayWorkflowResult> {
  const brief = await buildDayBrief(input, deps);

  return {
    text: formatTelegramPlanDay(brief),
    brief,
  };
}
