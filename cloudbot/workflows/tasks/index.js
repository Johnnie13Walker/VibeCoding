export const workflow = {
  name: "tasks",
  async run(context) {
    return {
      ok: false,
      workflow: "tasks",
      deprecated: true,
      message: "Legacy JS workflow disabled. Use Python Larisa runtime via cloudbot/workflows/tasks_summary.py."
    };
  }
};
