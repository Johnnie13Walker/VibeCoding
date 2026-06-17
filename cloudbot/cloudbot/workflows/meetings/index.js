export const workflow = {
  name: "meetings",
  async run(context) {
    return {
      ok: false,
      workflow: "meetings",
      deprecated: true,
      message: "Legacy JS workflow disabled. Use Python Larisa runtime via cloudbot/workflows/meetings_summary.py."
    };
  }
};
