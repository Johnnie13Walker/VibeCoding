export async function run(payload, providers) {
  return {
    skill: "todo_tasks",
    ok: true,
    payload,
    providers: Object.keys(providers || {})
  };
}
