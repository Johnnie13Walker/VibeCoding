function parseCommand(text) {
  const m = String(text || '').trim().match(/^\/(\w+)(?:\s+([\s\S]+))?$/);
  if (!m) return null;
  return {
    name: String(m[1] || '').toLowerCase(),
    arg: String(m[2] || '').trim(),
  };
}

function normalizeText(text) {
  return String(text || '').trim().toLowerCase();
}

function isDiagnosticsText(text) {
  const normalized = normalizeText(text);
  return normalized === 'diag'
    || normalized === 'диаг'
    || normalized === 'диагностика';
}

function isMeetingCreateText(text) {
  const normalized = normalizeText(text);
  return /(^|\s)(создай|запланируй|поставь)\s+встреч/i.test(normalized)
    || /(^|\s)встреч[ауы]\s+с\s+/i.test(normalized)
    || (/календар/i.test(normalized) && /встреч/i.test(normalized));
}

function resolveIntent(text) {
  const command = parseCommand(text);

  if (command) {
    if (command.name === 'diag') {
      return { intent: 'diagnostics', arg: command.arg, command };
    }
    if (command.name === 'day_briefing' || command.name === 'morning' || command.name === 'day') {
      return { intent: 'day_briefing', arg: command.arg, command };
    }
    if (command.name === 'tasks') {
      return { intent: 'tasks', arg: command.arg, command };
    }
    if (command.name === 'meetings') {
      return { intent: 'meeting_create', arg: command.arg, command };
    }
    if (command.name === 'whoop_report' || command.name === 'whoop_daily') {
      return { intent: 'whoop_report', arg: command.arg, command };
    }
    if (command.name === 'whoop_test' || command.name === 'whoop_telegram_test') {
      return { intent: 'whoop_report', arg: 'telegram-test', command };
    }
    if (command.name === 'whoop_discovery' || command.name === 'whoop_discover') {
      return { intent: 'whoop_report', arg: 'discover', command };
    }
    return { intent: 'legacy_contacts', arg: command.arg, command };
  }

  if (isDiagnosticsText(text)) {
    return { intent: 'diagnostics', arg: '', command: null };
  }

  if (isMeetingCreateText(text)) {
    return { intent: 'meeting_create', arg: String(text || '').trim(), command: null };
  }

  return { intent: 'legacy_contacts', arg: '', command: null };
}

export { parseCommand, resolveIntent };
