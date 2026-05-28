export function buildContext(input) {
  return {
    receivedAt: new Date().toISOString(),
    input,
    meta: { source: "cloudbot-orchestrator" }
  };
}
