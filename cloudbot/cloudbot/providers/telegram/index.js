export function createProvider(config = {}) {
  return {
    name: "telegram",
    config,
    async healthcheck() {
      return { provider: "telegram", ok: true };
    }
  };
}
