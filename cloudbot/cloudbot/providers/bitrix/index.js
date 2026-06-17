export function createProvider(config = {}) {
  return {
    name: "bitrix",
    config,
    async healthcheck() {
      return { provider: "bitrix", ok: true };
    }
  };
}
