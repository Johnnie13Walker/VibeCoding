export async function dispatchWorkflow(workflowName, registry, context) {
  const workflow = registry?.[workflowName];
  if (!workflow) {
    throw new Error(`Workflow not found: ${workflowName}`);
  }
  return workflow.run(context);
}
