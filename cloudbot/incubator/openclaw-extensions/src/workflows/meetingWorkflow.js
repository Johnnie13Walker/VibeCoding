import { findContacts } from '../../contacts/service.js';
import { createMeeting, getMeetings } from '../../provider.gcal.js';

const FLOW = 'meeting_create';

function nowIso() {
  return new Date().toISOString();
}

function normalizeText(text) {
  return String(text || '').trim();
}

function lower(text) {
  return normalizeText(text).toLowerCase();
}

function hasWord(raw, word) {
  const text = ` ${String(raw || '').toLowerCase()} `;
  return text.includes(` ${word} `);
}

function emptyPayload() {
  return {
    title: '',
    date: '',
    time: '',
    attendees: [],
    attendeesCandidates: [],
    duration: 30,
    description: '',
  };
}

function nextState(step, payload) {
  return {
    activeFlow: FLOW,
    step,
    payload,
    updatedAt: nowIso(),
  };
}

function response(text, reply_markup) {
  return {
    response: {
      text,
      ...(reply_markup ? { reply_markup } : {}),
    },
    nextState: null,
  };
}

function stateResponse(text, step, payload, reply_markup) {
  return {
    response: {
      text,
      ...(reply_markup ? { reply_markup } : {}),
    },
    nextState: nextState(step, payload),
  };
}

function toTwo(v) {
  return String(v).padStart(2, '0');
}

function todayYmd() {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());

  return {
    y: Number(fmt.find((x) => x.type === 'year')?.value),
    m: Number(fmt.find((x) => x.type === 'month')?.value),
    d: Number(fmt.find((x) => x.type === 'day')?.value),
  };
}

function parseDate(text) {
  const raw = lower(text);
  const today = todayYmd();

  if (hasWord(raw, 'сегодня')) {
    return `${today.y}-${toTwo(today.m)}-${toTwo(today.d)}`;
  }
  if (hasWord(raw, 'завтра')) {
    const dt = new Date(Date.UTC(today.y, today.m - 1, today.d + 1));
    return `${dt.getUTCFullYear()}-${toTwo(dt.getUTCMonth() + 1)}-${toTwo(dt.getUTCDate())}`;
  }
  if (hasWord(raw, 'послезавтра')) {
    const dt = new Date(Date.UTC(today.y, today.m - 1, today.d + 2));
    return `${dt.getUTCFullYear()}-${toTwo(dt.getUTCMonth() + 1)}-${toTwo(dt.getUTCDate())}`;
  }

  let m = raw.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) {
    const y = Number(m[1]);
    const mo = Number(m[2]);
    const d = Number(m[3]);
    if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31) return `${y}-${toTwo(mo)}-${toTwo(d)}`;
    return null;
  }

  m = raw.match(/(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?/);
  if (m) {
    const d = Number(m[1]);
    const mo = Number(m[2]);
    const y = Number(m[3] || today.y);
    if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31) return `${y}-${toTwo(mo)}-${toTwo(d)}`;
    return null;
  }

  return null;
}

function parseTime(text) {
  const m = normalizeText(text).match(/(\d{1,2})[:.\-](\d{2})/);
  if (!m) return null;
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (hh < 0 || hh > 23 || mm < 0 || mm > 59) return null;
  return `${toTwo(hh)}:${toTwo(mm)}`;
}

function parseDuration(text) {
  const m = lower(text).match(/(\d+)\s*(мин(?:ут[аы]?)?|час(?:а|ов)?)/);
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n <= 0) return null;
  if (m[2].startsWith('час')) return n * 60;
  return n;
}

function extractAttendeeFromText(text) {
  const m = normalizeText(text).match(/(?:^|\s)с\s+([а-яa-zё0-9@_.\-\s]+)$/iu);
  if (!m) return '';

  return String(m[1] || '')
    .replace(/\b(сегодня|завтра|послезавтра)\b/giu, ' ')
    .replace(/\b\d{1,2}[:.]\d{2}\b/g, ' ')
    .replace(/\b\d{1,2}\.\d{1,2}(?:\.\d{4})?\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractTitle(text) {
  const t = normalizeText(text)
    .replace(/^(создай|запланируй|поставь)\s+встреч[ауы]?/iu, '')
    .replace(/(^|\s)в\s+календар[ьею](?=\s|$)/giu, ' ')
    .replace(/(^|\s)(сегодня|завтра|послезавтра)(?=\s|$)/giu, ' ')
    .replace(/(^|\s)на\s+\d{1,2}\.\d{1,2}(?:\.\d{4})?(?=\s|$)/giu, ' ')
    .replace(/(^|\s)на\s+\d{4}-\d{1,2}-\d{1,2}(?=\s|$)/giu, ' ')
    .replace(/(^|\s)в\s*\d{1,2}[:.\-]\d{2}(?=\s|$)/giu, ' ')
    .replace(/(?:^|\s)с\s+[а-яa-zё0-9@_.\-\s]+$/iu, '')
    .replace(/^\s*(?:на|в)\s+/iu, ' ')
    .replace(/\s+(?:на|в)\s*$/iu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return t || 'Встреча';
}

function dateLabel(ymd) {
  const m = String(ymd || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return ymd;
  return `${m[3]}.${m[2]}.${m[1]}`;
}

function attendeeList(payload) {
  const list = Array.isArray(payload.attendees) ? payload.attendees : [];
  return list.map((x) => x.name).filter(Boolean).join(', ');
}

async function resolveAttendee(rawName, ctx) {
  const name = normalizeText(rawName);
  if (!name) return { kind: 'empty' };

  try {
    const scored = await findContacts(name, ctx);
    const top = Array.isArray(scored) ? scored.slice(0, 3) : [];

    if (top.length === 0) {
      return { kind: 'resolved', attendee: { name, source: 'text' } };
    }

    if (top.length === 1) {
      return {
        kind: 'resolved',
        attendee: {
          id: top[0].contact.id,
          name: top[0].contact.display_name,
          username: top[0].contact.tg_username || '',
          source: 'contacts',
        },
      };
    }

    const diff = Number(top[0].score || 0) - Number(top[1].score || 0);
    if (diff >= 8) {
      return {
        kind: 'resolved',
        attendee: {
          id: top[0].contact.id,
          name: top[0].contact.display_name,
          username: top[0].contact.tg_username || '',
          source: 'contacts',
        },
      };
    }

    return {
      kind: 'ambiguous',
      candidates: top.map((x, i) => ({
        index: i + 1,
        id: x.contact.id,
        name: x.contact.display_name,
        username: x.contact.tg_username || '',
      })),
    };
  } catch {
    return { kind: 'resolved', attendee: { name, source: 'text' } };
  }
}

function candidatesText(candidates) {
  const lines = (candidates || []).map((x) => `${x.index}. ${x.name}${x.username ? ` (${x.username})` : ''}`);
  return lines.join('\n');
}

function candidatesKeyboard(candidates) {
  const rows = (candidates || []).map((x) => [{ text: String(x.index) }]);
  return { keyboard: rows, resize_keyboard: true, one_time_keyboard: true };
}

async function finalizeMeeting(payload, ctx) {
  const attendeeNames = (payload.attendees || []).map((x) => x.name).filter(Boolean);
  const result = await createMeeting({
    title: payload.title || 'Встреча',
    date: payload.date,
    time: payload.time,
    duration: Number(payload.duration || 30),
    attendees: attendeeNames,
    description: payload.description || '',
  }, ctx);

  if (!result?.ok) {
    const errText = String(result?.text || 'неизвестная ошибка');
    if (/не нашел сотрудника|неоднозначно, кого пригласить|уточни фио/i.test(errText)) {
      const nextPayload = {
        ...payload,
        attendees: [],
        attendeesCandidates: [],
      };
      return stateResponse(
        `Не смог однозначно добавить участника в Bitrix.\n${errText}\n\nНапиши имя+фамилию или выбери другого сотрудника.`,
        'ask_attendees',
        nextPayload,
      );
    }
    return response(`Не удалось создать встречу: ${errText}`);
  }

  return response(result.text || 'Встреча создана.');
}

async function handleAskAttendees(inputText, payload, ctx) {
  const cleaned = normalizeText(inputText);
  if (!cleaned) {
    return stateResponse('Кого звать?', 'ask_attendees', payload);
  }

  const candidates = Array.isArray(payload.attendeesCandidates) ? payload.attendeesCandidates : [];
  const num = Number(cleaned);
  if (candidates.length > 0 && Number.isInteger(num) && num >= 1 && num <= candidates.length) {
    const picked = candidates[num - 1];
    const nextPayload = {
      ...payload,
      attendees: [{ id: picked.id, name: picked.name, username: picked.username }],
      attendeesCandidates: [],
    };

    if (!nextPayload.date) {
      return stateResponse(`Принял: ${picked.name}. На какую дату ставим встречу?`, 'ask_date', nextPayload);
    }
    if (!nextPayload.time) {
      return stateResponse(`Принял: ${picked.name}. Во сколько начать?`, 'ask_time', nextPayload);
    }
    return finalizeMeeting(nextPayload, ctx);
  }

  const resolved = await resolveAttendee(cleaned, ctx);
  if (resolved.kind === 'ambiguous') {
    const nextPayload = { ...payload, attendeesCandidates: resolved.candidates };
    return stateResponse(
      `Нужна уточнение по участнику. Выбери номер:\n${candidatesText(resolved.candidates)}`,
      'ask_attendees',
      nextPayload,
      candidatesKeyboard(resolved.candidates),
    );
  }

  if (resolved.kind !== 'resolved') {
    return stateResponse('Не понял участника. Кого звать?', 'ask_attendees', payload);
  }

  const nextPayload = {
    ...payload,
    attendees: [resolved.attendee],
    attendeesCandidates: [],
  };

  if (!nextPayload.date) {
    return stateResponse(`Кого звать понял: ${resolved.attendee.name}. На какую дату ставим встречу?`, 'ask_date', nextPayload);
  }
  if (!nextPayload.time) {
    return stateResponse(`Кого звать понял: ${resolved.attendee.name}. Во сколько начать?`, 'ask_time', nextPayload);
  }

  return finalizeMeeting(nextPayload, ctx);
}

async function handleAskDate(inputText, payload) {
  const date = parseDate(inputText);
  if (!date) {
    return stateResponse('Не понял дату. Напиши, например: завтра или 28.02.2026', 'ask_date', payload);
  }

  const nextPayload = { ...payload, date };
  if (!nextPayload.time) {
    return stateResponse(`Дата ${dateLabel(date)}. Во сколько начать?`, 'ask_time', nextPayload);
  }

  return stateResponse('Дата сохранена.', 'ask_time', nextPayload);
}

async function handleAskTime(inputText, payload, ctx) {
  const time = parseTime(inputText);
  if (!time) {
    return stateResponse('Не понял время. Напиши в формате 16:00', 'ask_time', payload);
  }

  const nextPayload = { ...payload, time, duration: Number(payload.duration || 30) };
  return finalizeMeeting(nextPayload, ctx);
}

function parseInitialPayload(text) {
  const payload = emptyPayload();
  payload.title = extractTitle(text);

  const attendee = extractAttendeeFromText(text);
  if (attendee) payload.attendeeRaw = attendee;

  const date = parseDate(text);
  if (date) payload.date = date;

  const time = parseTime(text);
  if (time) payload.time = time;

  const duration = parseDuration(text);
  if (duration) payload.duration = duration;

  return payload;
}

const meetingWorkflow = {
  async run(input, context = {}) {
    const commandName = String(context.command?.name || '').toLowerCase();
    if (commandName === 'meetings') {
      const query = String(context.arg || '').trim() || 'сегодня';
      const meetings = await getMeetings(query);
      return {
        response: { text: `Встречи (${query}):\n${meetings.text}` },
        nextState: null,
      };
    }

    const text = String(context.arg || input.text || '').trim();
    const payload = parseInitialPayload(text);

    if (!payload.attendeeRaw) {
      return stateResponse('Кого звать?', 'ask_attendees', payload);
    }

    const resolved = await resolveAttendee(payload.attendeeRaw, context);
    if (resolved.kind === 'ambiguous') {
      const nextPayload = {
        ...payload,
        attendeesCandidates: resolved.candidates,
      };
      return stateResponse(
        `Уточни участника:\n${candidatesText(resolved.candidates)}`,
        'ask_attendees',
        nextPayload,
        candidatesKeyboard(resolved.candidates),
      );
    }

    if (resolved.kind !== 'resolved') {
      return stateResponse('Кого звать?', 'ask_attendees', payload);
    }

    payload.attendees = [resolved.attendee];
    payload.attendeesCandidates = [];

    if (!payload.date) {
      return stateResponse('На какую дату ставим встречу?', 'ask_date', payload);
    }

    if (!payload.time) {
      return stateResponse('Во сколько начать?', 'ask_time', payload);
    }

    return finalizeMeeting(payload, context);
  },

  async continue(state, input, ctx = {}) {
    const step = String(state?.step || '').trim();
    const payload = {
      ...emptyPayload(),
      ...(state?.payload && typeof state.payload === 'object' ? state.payload : {}),
    };

    if (!Array.isArray(payload.attendees)) payload.attendees = [];
    if (!Array.isArray(payload.attendeesCandidates)) payload.attendeesCandidates = [];

    const inputText = String(input?.text || '').trim();

    if (step === 'ask_attendees') {
      return handleAskAttendees(inputText, payload, ctx);
    }

    if (step === 'ask_date') {
      return handleAskDate(inputText, payload, ctx);
    }

    if (step === 'ask_time') {
      return handleAskTime(inputText, payload, ctx);
    }

    return stateResponse('Сценарий устарел, начнем заново. Кого звать?', 'ask_attendees', emptyPayload());
  },
};

async function runMeetingsWorkflow(input, context = {}) {
  const out = await meetingWorkflow.run(input, context);
  return { handled: true, reply: out.response.text };
}

export { meetingWorkflow, runMeetingsWorkflow };
