function normTitle(s = "") {
  return String(s).toLowerCase().replace(/\s+/g, " ").trim();
}

function toMs(v) {
  const t = new Date(v).getTime();
  return Number.isFinite(t) ? t : null;
}

function near(a, b, deltaMs = 120000) {
  return Math.abs(a - b) <= deltaMs;
}

function uniqStrings(arr = []) {
  const out = [];
  const seen = new Set();
  for (const x of arr) {
    const s = String(x || "").trim();
    if (!s || seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  return out;
}

export function dedupeMeetings(meetings = []) {
  const out = [];

  for (const m of meetings) {
    const ms = toMs(m.start);
    const me = toMs(m.end);
    if (!ms || !me) continue;

    const title = normTitle(m.title);
    const same = out.find((x) => {
      const xs = toMs(x.start);
      const xe = toMs(x.end);
      if (!xs || !xe) return false;
      return near(xs, ms) && near(xe, me) && normTitle(x.title) === title;
    });

    if (!same) {
      out.push({ ...m, sources: [m.source] });
      continue;
    }

    const srcs = new Set([...(same.sources || [same.source]), m.source]);
    same.sources = [...srcs];
    same.source = same.source || m.source;
    if (!same.link && m.link) same.link = m.link;
    if (!same.location && m.location) same.location = m.location;

    same.attendeeIds = uniqStrings([...(same.attendeeIds || []), ...(m.attendeeIds || [])]);
    same.attendees = uniqStrings([...(same.attendees || []), ...(m.attendees || [])]);
  }

  return out.sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());
}
