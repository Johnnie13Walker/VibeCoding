export async function run(payload, providers) {
  return {
    skill: "gcal_query",
    ok: true,
    payload,
    providers: Object.keys(providers || {})
  };
}
