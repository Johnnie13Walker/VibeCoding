import { isBitrixAppNotConfiguredError, listBitrixMethod } from "./bitrixAppState.js";

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

function buildBitrixUsersUrl({ bitrixWebhookUrl, bitrixBaseUrl, bitrixToken, start }) {
  if (bitrixWebhookUrl) {
    const url = new URL(`${String(bitrixWebhookUrl).replace(/\/$/, "")}/user.get.json`);
    url.searchParams.set("start", String(start));
    return url;
  }

  const url = new URL(`${String(bitrixBaseUrl).replace(/\/$/, "")}/rest/user.get.json`);
  url.searchParams.set("auth", String(bitrixToken));
  url.searchParams.set("start", String(start));
  return url;
}

async function callBitrixListUsers({ bitrixWebhookUrl, bitrixBaseUrl, bitrixToken, timeoutMs = 9000 }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const users = [];
  let start = 0;

  try {
    while (true) {
      const url = buildBitrixUsersUrl({ bitrixWebhookUrl, bitrixBaseUrl, bitrixToken, start });
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) {
        throw new Error(`Bitrix users HTTP ${res.status}`);
      }
      const payload = await res.json();
      const batch = Array.isArray(payload?.result) ? payload.result : [];
      users.push(...batch);
      if (!payload?.next || batch.length === 0) {
        break;
      }
      start = Number(payload.next || 0);
      if (!Number.isFinite(start) || start <= 0) {
        break;
      }
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

      const hasAppAuth = Boolean(config.bitrixAppStateDir || config.bitrixAppInstallStateFile);
      const hasWebhookFallback = Boolean(
        config.bitrixWebhookUrl || (config.bitrixBaseUrl && config.bitrixToken)
      );

      if (!hasAppAuth && !hasWebhookFallback) {
        return { status: "not_configured", users: [] };
      }

      try {
        let rawUsers;
        let source = "bitrix_app";
        if (hasAppAuth) {
          rawUsers = await listBitrixMethod({
            config,
            method: "user.get"
          });
        } else {
          rawUsers = await callBitrixListUsers({
            bitrixWebhookUrl: config.bitrixWebhookUrl,
            bitrixBaseUrl: config.bitrixBaseUrl,
            bitrixToken: config.bitrixToken,
            timeoutMs: config.bitrixTimeoutMs
          });
          source = "bitrix_webhook";
        }
        const users = rawUsers.map(normalizeBitrixUser).filter(isActiveEmployee);
        return { status: "ok", users, source };
      } catch (error) {
        if (hasAppAuth && isBitrixAppNotConfiguredError(error) && hasWebhookFallback) {
          try {
            const rawUsers = await callBitrixListUsers({
              bitrixWebhookUrl: config.bitrixWebhookUrl,
              bitrixBaseUrl: config.bitrixBaseUrl,
              bitrixToken: config.bitrixToken,
              timeoutMs: config.bitrixTimeoutMs
            });
            const users = rawUsers.map(normalizeBitrixUser).filter(isActiveEmployee);
            return { status: "ok", users, source: "bitrix_webhook" };
          } catch (fallbackError) {
            logger.error?.(
              "[bitrixUsersProvider] fallback listActiveUsers failed",
              String(fallbackError?.message || fallbackError)
            );
            return { status: "error", users: [], error: String(fallbackError?.message || fallbackError) };
          }
        }
        if (hasAppAuth && isBitrixAppNotConfiguredError(error)) {
          return { status: "not_configured", users: [] };
        }
        logger.error?.("[bitrixUsersProvider] listActiveUsers failed", String(error?.message || error));
        return { status: "error", users: [], error: String(error?.message || error) };
      }
    }
  };
}
