export const workflow = {
  name: "notifications",
  async run(context) {
    return { ok: true, workflow: "notifications", context };
  }
};
