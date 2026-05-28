import { parseAddDraft } from "./add-parser.mjs";
import { addDaysISO, dateISOInTz } from "./time.mjs";
import { clearPending, getPending, setPending } from "./pending-state.mjs";
import {
  buildDateTimeByDateAndTime,
  buildMeetingFromDraft,
  cancelMeeting,
  createMeeting,
  detectMeetingDuplicate,
  extractPotentialNames,
  formatUsersMatches,
  getBitrixUsersCount,
  getBitrixUsersSyncMeta,
  getStoredDefaultSectionId,
  getMeetingById,
  listSections,
  moveMeeting,
  resolveUserMentions,
  searchMeetingsByText,
  setStoredDefaultSectionId,
  shiftIsoByMinutes,
  syncBitrixUsers,
  usersFind
} from "./agenda/providers/bitrixUsers.mjs";

function isYes(text) {
  return /^(да|ок|окей|yes|y|ага|подтверждаю)$/i.test(String(text || "").trim());
}

function isNo(text) {
  return /^(нет|no|n|отмена|cancel)$/i.test(String(text || "").trim());
}

function parseHHMM(text) {
  const m = String(text || "").match(/\b([01]?\d|2[0-3]):([0-5]\d)\b/);
  if (!m) return null;
  return `${m[1].padStart(2, "0")}:${m[2]}`;
}

function parseDurationMinutes(text) {
  const t = String(text || "");
  const r = t.match(/\b(\d{1,3})\s*(?:м|мин|минут)/i);
  if (r) return Math.max(10, Number(r[1]));
  const h = t.match(/\b(\d{1,2})\s*ч(?:ас|\.)?/i);
  if (h) return Math.max(15, Number(h[1]) * 60);
  const range = t.match(/\b([01]?\d|2[0-3]):([0-5]\d)\s*[-–]\s*([01]?\d|2[0-3]):([0-5]\d)\b/);
  if (range) {
    const s = Number(range[1]) * 60 + Number(range[2]);
    const e = Number(range[3]) * 60 + Number(range[4]);
    if (e > s) return e - s;
  }
  return 30;
}

function humanWhen(startIso, endIso) {
  const d = new Date(startIso);
  const d2 = new Date(endIso);
  const date = new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  const t1 = new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", hour: "2-digit", minute: "2-digit", hour12: false }).format(d);
  const t2 = new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", hour: "2-digit", minute: "2-digit", hour12: false }).format(d2);
  return `${date} ${t1}–${t2} (МСК)`;
}

function previewText(p) {
  return [
    "Создаю встречу:",
    `Название: ${p.title}`,
    `Когда: ${humanWhen(p.startIso, p.endIso)}`,
    `Участники: ${p.attendees.length ? p.attendees.map((x) => x.fullName).join(", ") : "без участников"}`,
    `Календарь: ${p.sectionTitle || p.sectionId || "default"}`,
    "Подтвердить? да/нет"
  ].join("\n");
}

function unresolvedPrompt(item) {
  if (!item?.candidates?.length) {
    return `Не нашёл сотрудника: '${item?.token || "?"}'.\nПроверь через /users_find ${item?.token || ""}`.trim();
  }
  const lines = [`Кого ты имел в виду под '${item.token}'?`];
  item.candidates.slice(0, 8).forEach((c, i) => {
    lines.push(`${i + 1}) ${c.fullName}${c.department ? ` (${c.department})` : ""}`);
  });
  lines.push("Ответь цифрой.");
  return lines.join("\n");
}

async function enrichSection(cfg, payload) {
  try {
    const sections = await listSections(cfg);
    const hit = sections.find((s) => String(s.id) === String(payload.sectionId));
    if (hit) payload.sectionTitle = hit.title;
  } catch {}
  return payload;
}

async function buildCreatePending(cfg, text) {
  const body = text.replace(/^\/meet_create\b/i, "").trim();
  if (!body) return { error: "Формат: /meet_create <текст встречи>" };

  const draft = parseAddDraft(body, cfg.tz);
  if (!draft.content) {
    return { error: "Не понял название встречи. Пример: /meet_create завтра 15:00 30м созвон с Денисом" };
  }

  const nameTokens = extractPotentialNames(body);
  const resolved = await resolveUserMentions(cfg, nameTokens);
  const durationMin = parseDurationMinutes(body);

  const base = buildMeetingFromDraft(draft, body, resolved.resolved);
  if (!base.startIso && !draft.parsed.noDate) {
    return {
      pending: {
        kind: "meeting",
        step: "meet_need_date",
        body,
        title: base.title,
        timeHHMM: draft.parsed.timeToken || null,
        durationMin,
        attendees: resolved.resolved,
        unresolved: resolved.unresolved
      }
    };
  }

  if (!draft.dueDateTime && !draft.parsed.timeToken && !body.match(/\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}/)) {
    return {
      pending: {
        kind: "meeting",
        step: "meet_need_time",
        body,
        title: base.title,
        dateIso: draft.dueDate || dateISOInTz(new Date(), cfg.tz),
        durationMin,
        attendees: resolved.resolved,
        unresolved: resolved.unresolved
      }
    };
  }

  if (resolved.unresolved.length) {
    return {
      pending: {
        kind: "meeting",
        step: "meet_resolve_person",
        body,
        title: base.title,
        startIso: base.startIso,
        endIso: base.endIso,
        durationMin,
        attendees: resolved.resolved,
        unresolved: resolved.unresolved,
        unresolvedIdx: 0
      }
    };
  }

  return {
    pending: {
      kind: "meeting",
      step: "meet_confirm",
      body,
      title: base.title,
      startIso: base.startIso,
      endIso: base.endIso,
      durationMin,
      attendees: resolved.resolved,
      unresolved: []
    }
  };
}

function ensureDateTime(p) {
  if (p.startIso && p.endIso) return p;
  if (p.dateIso && p.timeHHMM) {
    p.startIso = buildDateTimeByDateAndTime(p.dateIso, p.timeHHMM);
    p.endIso = shiftIsoByMinutes(p.startIso, Number(p.durationMin || 30));
  }
  return p;
}

async function preparePreview(cfg, p) {
  const payload = ensureDateTime({ ...p });
  if (!payload.startIso || !payload.endIso) return { error: "Не хватает даты/времени для встречи." };

  try {
    const sections = await listSections(cfg);
    const desired = String(cfg.bitrixDefaultSectionId || getStoredDefaultSectionId(cfg.stateDir) || "").trim();
    if (!desired) {
      const lines = ["Не задан BITRIX_DEFAULT_SECTION_ID. Выбери секцию:"];
      sections.slice(0, 15).forEach((s) => lines.push(`${s.id} — ${s.title}`));
      lines.push("Команда: /meet_section <id>");
      return { error: lines.join("\n") };
    }
    const hit = sections.find((x) => String(x.id) === desired);
    if (!hit) {
      const lines = ["BITRIX_DEFAULT_SECTION_ID недоступен. Выбери секцию:"];
      sections.slice(0, 15).forEach((s) => lines.push(`${s.id} — ${s.title}`));
      lines.push("Команда: /meet_section <id>");
      return { error: lines.join("\n") };
    }
    payload.sectionId = hit.id;
    payload.sectionTitle = hit.title;
  } catch (err) {
    return { error: `Не удалось получить секции: ${err.message || err}` };
  }

  return { payload: await enrichSection(cfg, payload) };
}

function parseMoveArgs(msg) {
  const body = msg.replace(/^\/meet_move\b/i, "").trim();
  const [id, ...rest] = body.split(/\s+/);
  if (!id || !rest.length) return null;
  return { id, target: rest.join(" ") };
}

export async function handleMeetingFlow(cfg, uid, msg) {
  let pending = getPending(cfg.stateDir, uid);
  if (/^\/(?:users_(?:sync|refresh|find|status)|meet_(?:create|move|cancel|section))\b/i.test(msg)) {
    if (pending?.kind === "meeting") {
      clearPending(cfg.stateDir, uid);
      pending = null;
    }
  }

  if (pending?.kind === "meeting") {
    if (pending.step === "meet_need_date") {
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        return { handled: true, text: "Ок, отменил создание встречи." };
      }
      const d = parseAddDraft(msg, cfg.tz);
      if (!d.dueDate && !d.dueDateTime && !d.parsed.noDate) {
        return { handled: true, text: "На какую дату поставить встречу? (сегодня/завтра/ДД.ММ/YYYY-MM-DD)" };
      }
      const next = { ...pending };
      if (d.dueDateTime) {
        next.startIso = d.dueDateTime;
      } else {
        next.dateIso = d.dueDate || dateISOInTz(new Date(), cfg.tz);
      }
      if (!next.startIso) {
        if (!next.timeHHMM) {
          next.step = "meet_need_time";
          setPending(cfg.stateDir, uid, next);
          return { handled: true, text: "Во сколько встреча? (HH:MM)" };
        }
        next.startIso = buildDateTimeByDateAndTime(next.dateIso, next.timeHHMM);
      }
      next.endIso = shiftIsoByMinutes(next.startIso, Number(next.durationMin || 30));
      next.step = next.unresolved?.length ? "meet_resolve_person" : "meet_confirm";
      setPending(cfg.stateDir, uid, next);
      if (next.step === "meet_resolve_person") return { handled: true, text: unresolvedPrompt(next.unresolved[next.unresolvedIdx || 0]) };
      const prep = await preparePreview(cfg, next);
      if (prep.error) return { handled: true, text: prep.error };
      setPending(cfg.stateDir, uid, { ...next, ...prep.payload, step: "meet_confirm" });
      return { handled: true, text: previewText({ ...next, ...prep.payload }) };
    }

    if (pending.step === "meet_need_time") {
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        return { handled: true, text: "Ок, отменил создание встречи." };
      }
      const hhmm = parseHHMM(msg);
      if (!hhmm) return { handled: true, text: "Не понял время. Напиши HH:MM" };
      const next = { ...pending, timeHHMM: hhmm };
      if (!next.dateIso && next.startIso) {
        const d = new Date(next.startIso);
        next.dateIso = dateISOInTz(d, cfg.tz);
      }
      next.startIso = buildDateTimeByDateAndTime(next.dateIso || dateISOInTz(new Date(), cfg.tz), hhmm);
      next.endIso = shiftIsoByMinutes(next.startIso, Number(next.durationMin || 30));
      next.step = next.unresolved?.length ? "meet_resolve_person" : "meet_confirm";
      setPending(cfg.stateDir, uid, next);
      if (next.step === "meet_resolve_person") return { handled: true, text: unresolvedPrompt(next.unresolved[next.unresolvedIdx || 0]) };
      const prep = await preparePreview(cfg, next);
      if (prep.error) return { handled: true, text: prep.error };
      setPending(cfg.stateDir, uid, { ...next, ...prep.payload, step: "meet_confirm" });
      return { handled: true, text: previewText({ ...next, ...prep.payload }) };
    }

    if (pending.step === "meet_resolve_person") {
      const idx = Number(String(msg || "").trim());
      const cur = pending.unresolved?.[pending.unresolvedIdx || 0];
      if (!cur) {
        const next = { ...pending, step: "meet_confirm" };
        setPending(cfg.stateDir, uid, next);
        const prep = await preparePreview(cfg, next);
        if (prep.error) return { handled: true, text: prep.error };
        setPending(cfg.stateDir, uid, { ...next, ...prep.payload });
        return { handled: true, text: previewText({ ...next, ...prep.payload }) };
      }

      if (!Number.isFinite(idx) || idx < 1 || idx > (cur.candidates?.length || 0)) {
        return { handled: true, text: unresolvedPrompt(cur) };
      }

      const selected = cur.candidates[idx - 1];
      const next = { ...pending };
      next.attendees = [...(next.attendees || []), selected];
      next.unresolvedIdx = Number(next.unresolvedIdx || 0) + 1;
      if (next.unresolvedIdx >= (next.unresolved?.length || 0)) {
        next.step = "meet_confirm";
        const prep = await preparePreview(cfg, next);
        if (prep.error) return { handled: true, text: prep.error };
        const finalP = { ...next, ...prep.payload };
        setPending(cfg.stateDir, uid, finalP);
        return { handled: true, text: previewText(finalP) };
      }
      setPending(cfg.stateDir, uid, next);
      return { handled: true, text: unresolvedPrompt(next.unresolved[next.unresolvedIdx]) };
    }

    if (pending.step === "meet_confirm_duplicate") {
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        return { handled: true, text: "Ок, не создаю дубль встречи." };
      }
      if (!isYes(msg)) return { handled: true, text: "Подтвердите: да/нет" };
      const out = await createMeeting(cfg, {
        title: pending.title,
        startIso: pending.startIso,
        endIso: pending.endIso,
        attendeesCodes: (pending.attendees || []).map((x) => `U${x.userId}`)
      }, { dryRun: cfg.bitrixCalendarDryRun });
      clearPending(cfg.stateDir, uid);
      if (out.dryRun) {
        return { handled: true, text: `DRY_RUN ✅\n${JSON.stringify(out.fields, null, 2)}` };
      }
      return { handled: true, text: `Готово ✅ Встреча создана. ID: ${out.eventId}\nread-back: IS_MEETING=true, ATTENDEES_CODES=${out.readback.attendeesCodes.join(",")}` };
    }

    if (pending.step === "meet_confirm") {
      if (isNo(msg)) {
        clearPending(cfg.stateDir, uid);
        return { handled: true, text: "Ок, создание встречи отменено." };
      }
      if (!isYes(msg)) return { handled: true, text: "Подтвердите: да/нет" };

      const dup = await detectMeetingDuplicate(cfg, {
        title: pending.title,
        startIso: pending.startIso,
        attendeesCodes: (pending.attendees || []).map((x) => `U${x.userId}`)
      }).catch(() => null);

      if (dup && !pending.duplicateConfirmed) {
        const next = { ...pending, step: "meet_confirm_duplicate", duplicateConfirmed: true };
        setPending(cfg.stateDir, uid, next);
        return {
          handled: true,
          text: `Похоже, такая встреча уже есть (ID ${dup.id}, ${dup.start}). Создать всё равно? да/нет`
        };
      }

      const out = await createMeeting(cfg, {
        title: pending.title,
        startIso: pending.startIso,
        endIso: pending.endIso,
        attendeesCodes: (pending.attendees || []).map((x) => `U${x.userId}`)
      }, { dryRun: cfg.bitrixCalendarDryRun });

      clearPending(cfg.stateDir, uid);
      if (out.dryRun) {
        return { handled: true, text: `DRY_RUN ✅\n${JSON.stringify(out.fields, null, 2)}` };
      }
      return { handled: true, text: `Готово ✅ Встреча создана. ID: ${out.eventId}\nread-back: IS_MEETING=true, ATTENDEES_CODES=${out.readback.attendeesCodes.join(",")}` };
    }
  }

  if (/^\/users_(sync|refresh)\b/i.test(msg)) {
    const res = await syncBitrixUsers(cfg, { force: true });
    if (!res.ok) return { handled: true, text: `Синк сотрудников: ошибка: ${res.error}` };
    return { handled: true, text: `Синк сотрудников завершён ✅ Активных: ${res.count}` };
  }

  if (/^\/users_find\b/i.test(msg)) {
    const q = msg.replace(/^\/users_find\b/i, "").trim();
    if (!q) return { handled: true, text: "Формат: /users_find <имя или фамилия>" };
    const rows = await usersFind(cfg, q, 10);
    return { handled: true, text: formatUsersMatches(rows) };
  }

  if (/^\/meet_section\b/i.test(msg)) {
    const arg = msg.replace(/^\/meet_section\b/i, "").trim();
    if (!arg) {
      const sections = await listSections(cfg).catch(() => []);
      if (!sections.length) return { handled: true, text: "Не удалось получить секции календаря." };
      const lines = ["Доступные секции:"];
      sections.slice(0, 20).forEach((s) => lines.push(`${s.id} — ${s.title}`));
      lines.push("Выбери: /meet_section <id>");
      return { handled: true, text: lines.join("\n") };
    }
    setStoredDefaultSectionId(cfg.stateDir, arg);
    return { handled: true, text: `Секция по умолчанию сохранена: ${arg}` };
  }

  if (/^\/meet_create\b/i.test(msg)) {
    const built = await buildCreatePending(cfg, msg);
    if (built.error) return { handled: true, text: built.error };
    const p = built.pending;
    if (p.step === "meet_need_date") {
      setPending(cfg.stateDir, uid, p);
      return { handled: true, text: "На какую дату поставить встречу? (сегодня/завтра/ДД.ММ/YYYY-MM-DD)" };
    }
    if (p.step === "meet_need_time") {
      setPending(cfg.stateDir, uid, p);
      return { handled: true, text: "Во сколько встреча? (HH:MM)" };
    }
    if (p.step === "meet_resolve_person") {
      setPending(cfg.stateDir, uid, p);
      return { handled: true, text: unresolvedPrompt(p.unresolved[0]) };
    }
    const prep = await preparePreview(cfg, p);
    if (prep.error) return { handled: true, text: prep.error };
    const finalP = { ...p, ...prep.payload };
    setPending(cfg.stateDir, uid, finalP);
    return { handled: true, text: previewText(finalP) };
  }

  if (/^\/meet_move\b/i.test(msg)) {
    const parsed = parseMoveArgs(msg);
    if (!parsed) return { handled: true, text: "Формат: /meet_move <id|поиск> <новая дата/время>" };

    let eventId = parsed.id;
    if (!/^\d+$/.test(eventId)) {
      const found = await searchMeetingsByText(cfg, eventId, dateISOInTz(new Date(), cfg.tz));
      if (!found.length) return { handled: true, text: "Не нашёл встречу по тексту." };
      eventId = found[0].id;
    }

    const ev = await getMeetingById(cfg, eventId);
    if (!ev) return { handled: true, text: "Встреча не найдена." };

    const d = parseAddDraft(parsed.target, cfg.tz);
    const hhmm = parseHHMM(parsed.target);
    if (!d.dueDate && !d.dueDateTime && !hhmm) {
      return { handled: true, text: "Не понял новое время. Пример: /meet_move 123 завтра 15:00" };
    }

    let startIso = d.dueDateTime || null;
    if (!startIso) {
      const dateIso = d.dueDate || dateISOInTz(new Date(), cfg.tz);
      if (!hhmm) return { handled: true, text: "Для переноса укажи время HH:MM" };
      startIso = buildDateTimeByDateAndTime(dateIso, hhmm);
    }

    const oldFrom = new Date(String(ev.DATE_FROM || ev.dateFrom || "").replace(" ", "T")).getTime();
    const oldTo = new Date(String(ev.DATE_TO || ev.dateTo || "").replace(" ", "T")).getTime();
    const dur = Number.isFinite(oldFrom) && Number.isFinite(oldTo) && oldTo > oldFrom ? Math.round((oldTo - oldFrom) / 60000) : 30;
    const endIso = shiftIsoByMinutes(startIso, dur);

    const res = await moveMeeting(cfg, eventId, startIso, endIso, { dryRun: cfg.bitrixCalendarDryRun });
    if (res.dryRun) return { handled: true, text: `DRY_RUN ✅\nmove meeting ${eventId} => ${humanWhen(startIso, endIso)}` };
    return { handled: true, text: `Готово ✅ Встреча ${eventId} перенесена на ${humanWhen(startIso, endIso)}.` };
  }

  if (/^\/meet_cancel\b/i.test(msg)) {
    const arg = msg.replace(/^\/meet_cancel\b/i, "").trim();
    if (!arg) return { handled: true, text: "Формат: /meet_cancel <id|поиск>" };

    if (pending?.kind === "meeting_cancel_confirm") {
      // no-op here; handled earlier
    }

    let eventId = arg;
    if (!/^\d+$/.test(eventId)) {
      const found = await searchMeetingsByText(cfg, eventId, dateISOInTz(new Date(), cfg.tz));
      if (!found.length) return { handled: true, text: "Не нашёл встречу по тексту." };
      eventId = found[0].id;
    }

    setPending(cfg.stateDir, uid, {
      kind: "meeting",
      step: "meet_cancel_confirm",
      eventId
    });
    return { handled: true, text: `Подтвердите отмену встречи ${eventId}: да/нет` };
  }

  if (pending?.kind === "meeting" && pending.step === "meet_cancel_confirm") {
    if (isNo(msg)) {
      clearPending(cfg.stateDir, uid);
      return { handled: true, text: "Ок, отмену встречи не делаю." };
    }
    if (!isYes(msg)) return { handled: true, text: "Подтвердите отмену: да/нет" };
    const res = await cancelMeeting(cfg, pending.eventId, { dryRun: cfg.bitrixCalendarDryRun });
    clearPending(cfg.stateDir, uid);
    if (res.dryRun) return { handled: true, text: `DRY_RUN ✅\ncancel meeting ${pending.eventId}` };
    return { handled: true, text: `Готово ✅ Встреча ${pending.eventId} отменена.` };
  }

  if (/^\/users_status\b/i.test(msg)) {
    const meta = getBitrixUsersSyncMeta(cfg.stateDir);
    const count = getBitrixUsersCount(cfg.stateDir);
    return { handled: true, text: `Bitrix users: ${meta.lastSyncStatus}\nlast: ${meta.lastSyncAt || "n/a"}\nactive: ${count}` };
  }

  return { handled: false, text: "" };
}
