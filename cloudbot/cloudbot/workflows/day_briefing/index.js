export const workflow = {
  name: "day_briefing",
  async run(context) {
    return {
      ok: false,
      workflow: "day_briefing",
      deprecated: true,
      message: "Legacy JS workflow disabled. Use Python Larisa runtime via cloudbot/workflows/day_briefing.py."
    };
  }
};
