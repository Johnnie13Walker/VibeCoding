export async function run(payload, providers) {
  return {
    skill: "whoop_data",
    ok: true,
    payload,
    providers: Object.keys(providers || {})
  };
}
