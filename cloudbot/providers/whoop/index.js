export function createProvider(config = {}) {
  return {
    name: "whoop",
    config,
    async healthcheck() {
      return { provider: "whoop", ok: true };
    }
  };
}
