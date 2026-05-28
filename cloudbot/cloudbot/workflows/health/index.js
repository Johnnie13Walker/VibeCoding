export const workflow = {
  name: "health",
  async run(context) {
    return { ok: true, workflow: "health", context };
  }
};
