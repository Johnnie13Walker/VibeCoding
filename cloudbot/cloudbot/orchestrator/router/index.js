export function selectWorkflow(intent) {
  const table = {
    day_briefing: "day_briefing",
    tasks: "tasks",
    meetings: "meetings",
    health: "health",
    notifications: "notifications",
    sales: "sales_brief",
    pipeline: "sales_brief",
    risks: "sales_brief",
    focus: "sales_brief",
    bitrixcheck: "bitrix_check"
  };

  return table[intent] || "day_briefing";
}
