import { classifyBitrixEvent, renderDailyCalendarDigest } from "../reports/calendarDailyRenderer.mjs";

const myUserCode = "U12";
const dateIso = "2026-03-04";

const mockEvents = [
  {
    id: "m1",
    title: "Встреча с Романом",
    start: `${dateIso}T08:30:00+03:00`,
    end: `${dateIso}T09:00:00+03:00`,
    ATTENDEES_CODES: ["U12", "U77"],
    attendees: ["Роман"]
  },
  {
    id: "w1",
    title: "Подготовить отчёт",
    start: `${dateIso}T10:00:00+03:00`,
    end: `${dateIso}T11:00:00+03:00`,
    ATTENDEES_CODES: ["U12"]
  },
  {
    id: "p1",
    title: "Обед",
    start: `${dateIso}T13:00:00+03:00`,
    end: `${dateIso}T14:00:00+03:00`,
    ATTENDEES_CODES: ["U12"]
  }
];

const expectedTypes = ["meeting", "work_block", "personal_block"];
const actualTypes = mockEvents.map((event) => classifyBitrixEvent(event, myUserCode));

if (JSON.stringify(expectedTypes) !== JSON.stringify(actualTypes)) {
  throw new Error(`calendar_renderer_smoke: classify mismatch expected=${JSON.stringify(expectedTypes)} actual=${JSON.stringify(actualTypes)}`);
}

const digest = renderDailyCalendarDigest({
  agenda: {
    date: dateIso,
    meetings: mockEvents,
    freeSlots: [{ start: "15:00", end: "17:00" }]
  },
  cfg: { tz: "Europe/Moscow", bitrixUserId: "12" },
  myUserCode
});

const mustContain = [
  "🤝 <b>ВСТРЕЧИ</b>",
  "🧠 <b>МОИ БЛОКИ РАБОТЫ</b>",
  "🍽 <b>ЛИЧНОЕ</b>",
  "🟢 <b>ОКНО ФОКУСА</b>",
  "➡️ <b>НАЧАТЬ СЕЙЧАС</b>"
];
mustContain.forEach((part) => {
  if (!digest.includes(part)) {
    throw new Error(`calendar_renderer_smoke: missing block ${part}`);
  }
});

console.log("calendar_renderer_smoke_output:");
console.log(digest);
console.log("calendar_renderer_smoke: ok");
