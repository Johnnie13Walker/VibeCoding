export async function run(payload, providers) {
  return {
    skill: "bitrix_add_event",
    ok: true,
    payload,
    providers: Object.keys(providers || {})
  };
}
