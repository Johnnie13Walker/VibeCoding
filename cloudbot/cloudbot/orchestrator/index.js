import { selectWorkflow } from "./router/index.js";
import { dispatchWorkflow } from "./dispatcher/index.js";
import { buildContext } from "./context/index.js";

export async function handleIncomingMessage(input, registry) {
  const context = buildContext(input);
  const workflowName = selectWorkflow(input?.intent || "day_briefing");
  return dispatchWorkflow(workflowName, registry, context);
}
