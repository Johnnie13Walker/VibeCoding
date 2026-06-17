export async function run(payload, providers) {
  return {
    skill: "web_search",
    ok: true,
    payload,
    providers: Object.keys(providers || {})
  };
}
