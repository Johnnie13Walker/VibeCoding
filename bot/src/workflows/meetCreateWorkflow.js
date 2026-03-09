export function extractAttendeeQuery(text) {
  const raw = String(text || "").trim();
  const m = raw.match(/встреч[ау]\s+с\s+(.+)$/i);
  if (!m) return "";
  return m[1].trim();
}

function candidateLabel(user) {
  const role = user.workPosition ? ` (${user.workPosition})` : "";
  return `${user.fullName}${role}`;
}

function buildInlineKeyboard(candidates) {
  return {
    inline_keyboard: candidates.map((u, idx) => [
      {
        text: `${idx + 1}. ${candidateLabel(u)}`,
        callback_data: `pick_attendee:${idx + 1}`
      }
    ])
  };
}

export async function handleMeetCreateAttendee({ state, text, resolver }) {
  const attendeeQuery = extractAttendeeQuery(text) || String(text || "").trim();
  const resolved = await resolver.resolvePerson(attendeeQuery);

  if (resolved.type === "single") {
    state.step = "ask_date";
    state.payload = {
      ...(state.payload || {}),
      attendeeIds: [String(resolved.user.id)],
      attendeeNames: [resolved.user.fullName]
    };

    return {
      state,
      response: {
        text: `Ок, встреча с ${resolved.user.fullName}. Напиши дату и время.`
      }
    };
  }

  if (resolved.type === "multiple") {
    state.step = "pick_attendee";
    state.payload = {
      ...(state.payload || {}),
      attendeeQuery,
      candidates: resolved.candidates.map((u) => ({
        id: String(u.id),
        fullName: u.fullName,
        workPosition: u.workPosition
      }))
    };

    const lines = resolved.candidates
      .map((u, idx) => `${idx + 1}) ${candidateLabel(u)}`)
      .join("\n");

    return {
      state,
      response: {
        text: `Нашел несколько вариантов:\n${lines}\nВыбери кнопкой или ответь цифрой 1-${resolved.candidates.length}.`,
        reply_markup: buildInlineKeyboard(resolved.candidates)
      }
    };
  }

  if (resolved.type === "not_configured") {
    state.step = "ask_attendees";
    return {
      state,
      response: {
        text: "Bitrix доступ не настроен, не могу подтянуть сотрудников. Напиши ФИО полностью или настрой доступ."
      }
    };
  }

  state.step = "ask_attendees";
  return {
    state,
    response: {
      text: "Не нашел такого сотрудника. Напиши фамилию или имя+фамилию."
    }
  };
}

export function handlePickAttendee({ state, text, callbackData }) {
  const candidates = state?.payload?.candidates || [];
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return {
      state,
      response: { text: "Список кандидатов пуст. Напиши сотрудника еще раз." }
    };
  }

  let pickIndex = -1;
  if (callbackData && /^pick_attendee:\d+$/.test(callbackData)) {
    pickIndex = Number(callbackData.split(":")[1]) - 1;
  } else if (/^\d+$/.test(String(text || "").trim())) {
    pickIndex = Number(String(text).trim()) - 1;
  }

  if (pickIndex < 0 || pickIndex >= candidates.length) {
    return {
      state,
      response: { text: `Неверный выбор. Введи число от 1 до ${candidates.length}.` }
    };
  }

  const chosen = candidates[pickIndex];
  state.step = "ask_date";
  state.payload = {
    ...(state.payload || {}),
    attendeeIds: [String(chosen.id)],
    attendeeNames: [chosen.fullName],
    candidates: undefined
  };

  return {
    state,
    response: {
      text: `Выбрал: ${chosen.fullName}. Теперь напиши дату и время.`
    }
  };
}
