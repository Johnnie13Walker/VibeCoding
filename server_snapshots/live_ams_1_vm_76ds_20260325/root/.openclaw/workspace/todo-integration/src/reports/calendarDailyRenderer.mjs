function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function cleanText(v = "") {
  return String(v || "").replace(/\s+/g, " ").trim();
}

function asArray(v) {
  return Array.isArray(v) ? v : [];
}

function normalizeUserToken(v) {
  const raw = cleanText(v);
  if (!raw) return null;
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return { id: m[1], code: `U${m[1]}`, raw };
  if (/^\d+$/.test(raw)) return { id: raw, code: `U${raw}`, raw };
  return { id: null, code: raw.toUpperCase(), raw };
}

function buildIdentity(input) {
  const ids = new Set();
  const codes = new Set();

  const add = (value) => {
    const t = normalizeUserToken(value);
    if (!t) return;
    if (t.id) ids.add(t.id);
    if (t.code) codes.add(t.code);
  };

  if (input && typeof input === "object" && !Array.isArray(input)) {
    add(input.myUserId);
    add(input.myUserCode);
    add(input.userId);
    add(input.userCode);
    add(input.id);
    add(input.code);
  } else {
    add(input);
  }

  return { ids, codes };
}

function isSelf(value, identity) {
  const t = normalizeUserToken(value);
  if (!t) return false;
  if (t.id && identity.ids.has(t.id)) return true;
  if (t.code && identity.codes.has(t.code)) return true;
  return false;
}

function isPersonalTitle(title = "") {
  return /(обед|еда|спорт|трен|дорога|перерыв|врач|семья|садик|школа)/i.test(String(title || ""));
}

function hasOwn(obj, key) {
  return !!(obj && Object.prototype.hasOwnProperty.call(obj, key));
}

function collectMeetingParticipants(event) {
  const values = [];
  let hasField = false;

  if (event?.MEETING && typeof event.MEETING === "object") {
    hasField = true;
    values.push(...asArray(event.MEETING.PARTICIPANTS));
    values.push(...asArray(event.MEETING.PARTICIPANTS_CODES));
    values.push(...asArray(event.MEETING.USERS));
    if (event.MEETING.HOST != null) values.push(event.MEETING.HOST);
  }

  if (event?.host != null) {
    hasField = true;
    values.push(event.host);
  }
  if (event?.HOST != null) {
    hasField = true;
    values.push(event.HOST);
  }
  if (hasOwn(event, "participants")) {
    hasField = true;
    values.push(...asArray(event.participants));
  }
  if (hasOwn(event, "PARTICIPANTS")) {
    hasField = true;
    values.push(...asArray(event.PARTICIPANTS));
  }

  return { values, hasField };
}

function extractParticipantToken(entry) {
  if (entry == null) return null;
  if (typeof entry === "string" || typeof entry === "number") return entry;
  if (typeof entry !== "object") return null;
  return (
    entry.USER_ID
    ?? entry.userId
    ?? entry.ID
    ?? entry.id
    ?? entry.ENTITY_ID
    ?? entry.entityId
    ?? entry.CODE
    ?? entry.code
    ?? entry.USER_CODE
    ?? entry.userCode
    ?? null
  );
}

function hasOthersInList(values, identity) {
  const filtered = values
    .map((entry) => extractParticipantToken(entry) ?? entry)
    .map((entry) => cleanText(entry))
    .filter(Boolean);
  if (!filtered.length) return false;
  return filtered.some((x) => !isSelf(x, identity));
}

export function classifyBitrixEvent(event, myUserIdOrCode) {
  const identity = buildIdentity(myUserIdOrCode);
  const title = String(event?.title || event?.NAME || event?.name || "");

  const hasCodesField = hasOwn(event, "ATTENDEES_CODES") || hasOwn(event, "attendeesCodes");
  if (hasCodesField) {
    const codes = [...asArray(event?.ATTENDEES_CODES), ...asArray(event?.attendeesCodes)];
    if (hasOthersInList(codes, identity)) return "meeting";
    return isPersonalTitle(title) ? "personal_block" : "work_block";
  }

  const hasAttendeesField = hasOwn(event, "attendees") || hasOwn(event, "ATTENDEES") || hasOwn(event, "ATTENDEE_LIST");
  if (hasAttendeesField) {
    const attendees = [...asArray(event?.attendees), ...asArray(event?.ATTENDEES), ...asArray(event?.ATTENDEE_LIST)];
    if (hasOthersInList(attendees, identity)) return "meeting";
    return isPersonalTitle(title) ? "personal_block" : "work_block";
  }

  const isMeetingFlag = event?.IS_MEETING === true || event?.isMeeting === true || String(event?.IS_MEETING || "").toLowerCase() === "true";
  const participants = collectMeetingParticipants(event);
  if (isMeetingFlag && participants.hasField) {
    if (hasOthersInList(participants.values, identity)) return "meeting";
    return isPersonalTitle(title) ? "personal_block" : "work_block";
  }

  return "work_block";
}

function normalizeFallbackUser(entry) {
  const raw = cleanText(entry);
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw;
}

function displayNameFromObject(obj = {}) {
  const full = cleanText(obj.FULL_NAME || obj.fullName || obj.DISPLAY_NAME || obj.displayName);
  if (full) return full;
  const first = cleanText(obj.NAME || obj.name || obj.FIRST_NAME || obj.firstName);
  const last = cleanText(obj.LAST_NAME || obj.lastName || obj.SURNAME || obj.surname);
  const joined = cleanText(`${first} ${last}`);
  if (joined) return joined;
  const title = cleanText(obj.TITLE || obj.title);
  if (title) return title;
  const email = cleanText(obj.EMAIL || obj.email);
  if (email) return email;
  const login = cleanText(obj.LOGIN || obj.login);
  if (login) return login;

  const token = extractParticipantToken(obj);
  return normalizeFallbackUser(token);
}

function pushUnique(out, seen, value) {
  const clean = cleanText(value);
  if (!clean) return;
  if (clean === "[object Object]") return;
  if (seen.has(clean.toLowerCase())) return;
  seen.add(clean.toLowerCase());
  out.push(clean);
}

export function extractOtherAttendees(event, myUserCode) {
  const identity = buildIdentity(myUserCode);
  const out = [];
  const seen = new Set();

  const attendeeArrays = [event?.attendees, event?.ATTENDEES, event?.ATTENDEE_LIST];
  attendeeArrays.forEach((arr) => {
    asArray(arr).forEach((entry) => {
      if (typeof entry === "string" || typeof entry === "number") {
        if (isSelf(entry, identity)) return;
        const name = normalizeFallbackUser(entry);
        pushUnique(out, seen, name);
        return;
      }
      if (entry && typeof entry === "object") {
        const token = extractParticipantToken(entry);
        if (token != null && isSelf(token, identity)) return;
        const name = displayNameFromObject(entry);
        pushUnique(out, seen, name);
      }
    });
  });

  const fallbackTokens = [
    ...asArray(event?.attendeeIds),
    ...asArray(event?.ATTENDEES_CODES),
    ...asArray(event?.attendeesCodes),
    ...collectMeetingParticipants(event).values.map((x) => extractParticipantToken(x) ?? x)
  ];

  fallbackTokens.forEach((token) => {
    if (token == null || isSelf(token, identity)) return;
    const display = normalizeFallbackUser(token);
    pushUnique(out, seen, display);
  });

  return out;
}

function pluralRu(n, one, few, many) {
  const v = Math.abs(Number(n || 0)) % 100;
  const rem = v % 10;
  if (v > 10 && v < 20) return many;
  if (rem > 1 && rem < 5) return few;
  if (rem === 1) return one;
  return many;
}

function dateIsoNow(tz = "Europe/Moscow") {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const d = parts.find((p) => p.type === "day")?.value;
  if (!y || !m || !d) return "1970-01-01";
  return `${y}-${m}-${d}`;
}

function dateTitle(dateISO, tz = "Europe/Moscow") {
  const dt = new Date(`${dateISO}T00:00:00+03:00`);
  if (!Number.isFinite(dt.getTime())) return dateISO;
  const raw = new Intl.DateTimeFormat("ru-RU", {
    timeZone: tz,
    weekday: "long",
    day: "numeric",
    month: "long"
  }).format(dt);
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function hhmm(dt, tz = "Europe/Moscow") {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(dt));
}

function eventRange(event, tz) {
  if (event?.isAllDay) return "Весь день";
  const start = new Date(event?.start || "");
  const end = new Date(event?.end || "");
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime())) return "Время уточняется";
  return `${hhmm(start, tz)}–${hhmm(end, tz)}`;
}

function slotDurationMin(slot) {
  const a = String(slot?.start || "").match(/^(\d{2}):(\d{2})$/);
  const b = String(slot?.end || "").match(/^(\d{2}):(\d{2})$/);
  if (!a || !b) return 0;
  const s = Number(a[1]) * 60 + Number(a[2]);
  const e = Number(b[1]) * 60 + Number(b[2]);
  return Math.max(0, e - s);
}

function sortByStart(events) {
  return [...events].sort((a, b) => {
    const sa = new Date(a?.start || 0).getTime();
    const sb = new Date(b?.start || 0).getTime();
    if (sa !== sb) return sa - sb;
    const ea = new Date(a?.end || 0).getTime();
    const eb = new Date(b?.end || 0).getTime();
    return ea - eb;
  });
}

function limitLinesByItems(items, toLines, maxContentLines = 6) {
  const lines = [];
  let shownItems = 0;

  for (let i = 0; i < items.length; i += 1) {
    const chunk = toLines(items[i]);
    if (lines.length + chunk.length > maxContentLines) break;
    lines.push(...chunk);
    shownItems += 1;
  }

  if (shownItems < items.length) {
    lines.push(`+${items.length - shownItems}`);
  }

  return lines;
}

function buildRisks({ meetingCount, workCount, focusWindows }) {
  const totalFocusMin = focusWindows.reduce((acc, slot) => acc + slotDurationMin(slot), 0);
  const out = [];

  if (totalFocusMin < 90) {
    out.push("Мало времени для фокус-работы");
  }
  if (meetingCount >= 7) {
    out.push("Перегруз встречами — может просесть выполнение задач");
  }
  if (workCount === 0) {
    out.push("Нет выделенных рабочих блоков");
  }

  return out.slice(0, 3);
}

function normalizeMyUserCode(input) {
  const raw = cleanText(input);
  if (!raw) return "";
  const m = raw.match(/^[Uu](\d+)$/);
  if (m) return `U${m[1]}`;
  if (/^\d+$/.test(raw)) return `U${raw}`;
  return raw.toUpperCase();
}

export function renderDailyCalendarDigest(data) {
  const agenda = data?.agenda || data || {};
  const cfg = data?.cfg || {};
  const tz = data?.tz || cfg?.tz || "Europe/Moscow";
  const myUserCode = normalizeMyUserCode(data?.myUserCode || data?.myUserId || cfg?.bitrixUserId || "");
  const events = sortByStart(asArray(agenda?.meetings));

  const buckets = {
    meeting: [],
    work_block: [],
    personal_block: []
  };

  events.forEach((event) => {
    const type = classifyBitrixEvent(event, { myUserCode, myUserId: cfg?.bitrixUserId });
    if (!buckets[type]) buckets.work_block.push(event);
    else buckets[type].push(event);
  });

  const focusWindows = asArray(agenda?.freeSlots).filter((slot) => slotDurationMin(slot) >= 45);
  const risks = buildRisks({
    meetingCount: buckets.meeting.length,
    workCount: buckets.work_block.length,
    focusWindows
  });

  const todayIso = cleanText(agenda?.date) || dateIsoNow(tz);
  const summary = [
    `${buckets.meeting.length} ${pluralRu(buckets.meeting.length, "встреча", "встречи", "встреч")}`,
    `${buckets.work_block.length} ${pluralRu(buckets.work_block.length, "блок работы", "блока работы", "блоков работы")}`,
    `${buckets.personal_block.length} ${pluralRu(buckets.personal_block.length, "личный блок", "личных блока", "личных блоков")}`,
    `${focusWindows.length} ${pluralRu(focusWindows.length, "окно фокуса", "окна фокуса", "окон фокуса")}`
  ].join(" • ");

  const blocks = [];

  if (buckets.meeting.length) {
    const lines = limitLinesByItems(buckets.meeting, (event) => {
      const base = [`${eventRange(event, tz)}  ${escapeHtml(cleanText(event?.title || "Без названия"))}`];
      const attendees = extractOtherAttendees(event, myUserCode);
      if (attendees.length) {
        const shown = attendees.slice(0, 5).map((name) => escapeHtml(cleanText(name)));
        const extra = attendees.length > shown.length ? `, +${attendees.length - shown.length}` : "";
        base.push(`(${shown.join(", ")}${extra})`);
      }
      return base;
    });
    blocks.push({ title: "🤝 <b>ВСТРЕЧИ</b>", lines });
  }

  if (buckets.work_block.length) {
    const lines = limitLinesByItems(
      buckets.work_block,
      (event) => [`${eventRange(event, tz)}  ${escapeHtml(cleanText(event?.title || "Без названия"))}`]
    );
    blocks.push({ title: "🧠 <b>МОИ БЛОКИ РАБОТЫ</b>", lines });
  }

  if (buckets.personal_block.length) {
    const lines = limitLinesByItems(
      buckets.personal_block,
      (event) => [`${eventRange(event, tz)}  ${escapeHtml(cleanText(event?.title || "Без названия"))}`]
    );
    blocks.push({ title: "🍽 <b>ЛИЧНОЕ</b>", lines });
  }

  if (focusWindows.length) {
    const lines = limitLinesByItems(
      focusWindows,
      (slot) => [`${slot.start}–${slot.end}  глубокая работа`]
    );
    blocks.push({ title: "🟢 <b>ОКНО ФОКУСА</b>", lines });
  } else {
    blocks.push({ title: "", lines: ["⚠️ <b>Нет свободных окон</b>"] });
  }

  if (risks.length) {
    blocks.push({ title: "⚠️ <b>РИСКИ ДНЯ</b>", lines: risks.map((risk) => `• ${escapeHtml(risk)}`) });
  }

  const firstWork = buckets.work_block[0] || null;
  blocks.push({
    title: "➡️ <b>НАЧАТЬ СЕЙЧАС</b>",
    lines: [
      firstWork
        ? `${eventRange(firstWork, tz)}  ${escapeHtml(cleanText(firstWork?.title || "Без названия"))}`
        : "Выбери главный фокус"
    ]
  });

  const out = [
    `☀️ <b>${escapeHtml(dateTitle(todayIso, tz))}</b>`,
    "",
    `📊 День: ${summary}`
  ];

  blocks.forEach((block) => {
    if (!block.lines?.length) return;
    out.push("", "────────", "");
    if (block.title) out.push(block.title);
    out.push(...block.lines);
  });

  return out.join("\n");
}
