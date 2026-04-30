export function createProvider(config = {}) {
  return {
    name: "search",
    config,
    async healthcheck() {
      return { provider: "search", ok: true };
    }
  };
}
