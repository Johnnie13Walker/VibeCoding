export function createProvider(config = {}) {
  return {
    name: "todoist",
    config,
    async healthcheck() {
      return { provider: "todoist", ok: true };
    }
  };
}
