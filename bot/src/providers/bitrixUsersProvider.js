const TERMINATED_KEYS = [
  "UF_EMPLOYMENT_DATE",
  "UF_DISMISSAL_DATE",
  "UF_USER_DISMISSAL_DATE",
  "UF_TERMINATED",
  "UF_FIRED",
  "UF_IS_EX_EMPLOYEE",
  "UF_EX_EMPLOYEE"
];

function normalizeBitrixUser(raw) {
  const id = raw.ID ?? raw.id;
  const name = raw.NAME ?? raw.name ?? "";
  const lastName = raw.LAST_NAME ?? raw.last_name ?? "";
  const secondName = raw.SECOND_NAME ?? raw.second_name ?? "";
  const workPosition = raw.WORK_POSITION ?? raw.work_position ?? "";
  const email = raw.EMAIL ?? raw.email ?? "";
  const active = String(raw.ACTIVE ?? raw.active ?? "Y") === "Y";

  const terminationSignals = TERMINATED_KEYS.map((key) => raw[key]).filter(
    (v) => v !== undefined && v !== null && v !== ""
  );

  const isExEmployeeField = raw.UF_IS_EX_EMPLOYEE ?? raw.UF_EX_EMPLOYEE;
  const isExEmployee =
    isExEmployeeField === undefined
      ? undefined
      : String(isExEmployeeField) === "1" || String(isExEmployeeField).toLowerCase() === "true";

  const terminated =
    terminationSignals.length > 0 ||
    (raw.STATUS && String(raw.STATUS).toLowerCase().includes("dismiss")) ||
    false;

  const fullName = [lastName, name, secondName].filter(Boolean).join(" ") || [name, lastName].filter(Boolean).join(" ");

  return {
    id,
    name,
    lastName,
    secondName: secondName || undefined,
    fullName,
    email: email || undefined,
    workPosition: workPosition || undefined,
    active,
    terminated: terminated || undefined,
    isExEmployee
  };
}

function isActiveEmployee(user) {
  if (!user.active) return false;
  if (user.isExEmployee === true) return false;
  if (user.terminated === true) return false;
  return true;
}

async function callBitrixListUsers({ bitrixBaseUrl, bitrixToken, timeoutMs = 9000 }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const users = [];
  let start = 0;

  try {
    while (true) {
      const url = new URL(`${bitrixBaseUrl.replace(/\/$/, "")}/rest/user.get.json`);
      url.searchParams.set("auth", bitrixToken);
      url.searchParams.set("start", String(start));

      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) {
        throw new Error(`Bitrix HTTP ${res.status}`);
      }
      const body = await res.json();
      if (body.error) {
        throw new Error(`Bitrix error: ${body.error_description || body.error}`);
      }

      const chunk = Array.isArray(body.result) ? body.result : [];
      users.push(...chunk);

      const next = body.next;
      if (next === undefined || next === null || Number(next) <= start || chunk.length === 0) {
        break;
      }
      start = Number(next);
    }
  } finally {
    clearTimeout(timer);
  }

  return users;
}

export function createBitrixUsersProvider({ config, logger = console }) {
  return {
    async listActiveUsers() {
      if (config.useFixtureUsers) {
        const { readFile } = await import("node:fs/promises");
        const raw = JSON.parse(await readFile(config.fixtureUsersFile, "utf-8"));
        const users = raw.map(normalizeBitrixUser).filter(isActiveEmployee);
        return { status: "ok", users, source: "fixture" };
      }

      if (!config.bitrixBaseUrl || !config.bitrixToken) {
        return { status: "not_configured", users: [] };
      }

      try {
        const rawUsers = await callBitrixListUsers({
          bitrixBaseUrl: config.bitrixBaseUrl,
          bitrixToken: config.bitrixToken
        });
        const users = rawUsers.map(normalizeBitrixUser).filter(isActiveEmployee);
        return { status: "ok", users, source: "bitrix" };
      } catch (error) {
        logger.error?.("[bitrixUsersProvider] listActiveUsers failed", error);
        return { status: "error", users: [], error: String(error?.message || error) };
      }
    }
  };
}
