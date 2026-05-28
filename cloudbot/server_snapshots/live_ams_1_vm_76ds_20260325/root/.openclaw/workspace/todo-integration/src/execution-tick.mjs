import { runExecutionTick } from "./execution/executionEngine.mjs";

async function main() {
  const r = await runExecutionTick();
  if (r.skipped) {
    console.log(`execution_skip reason=${r.reason}`);
    return;
  }
  console.log(`execution_ok sent=${r.sent ? 1 : 0} type=${r.sentType || "none"} now=${r.nowHHMM} inMeeting=${r.inMeeting ? 1 : 0} free=${r.freeUntilNextMeeting ?? -1} nextMeetingIn=${r.minutesToNextMeeting ?? -1}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
