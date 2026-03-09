import path from "node:path";
import { mkdir, readFile, writeFile } from "node:fs/promises";

export async function readUsersCache(cacheFile) {
  try {
    const raw = await readFile(cacheFile, "utf-8");
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.users) || typeof parsed.updatedAt !== "string") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export async function writeUsersCache(cacheFile, users) {
  await mkdir(path.dirname(cacheFile), { recursive: true });
  const payload = {
    updatedAt: new Date().toISOString(),
    users
  };
  await writeFile(cacheFile, JSON.stringify(payload, null, 2), "utf-8");
  return payload;
}

export async function getUsersWithCache({ cacheFile, ttlMs, provider, logger = console }) {
  const cached = await readUsersCache(cacheFile);
  const now = Date.now();
  if (cached) {
    const age = now - Date.parse(cached.updatedAt);
    if (Number.isFinite(age) && age <= ttlMs) {
      return { status: "ok", users: cached.users, cache: "hit_fresh", updatedAt: cached.updatedAt };
    }
  }

  const result = await provider.listActiveUsers();
  if (result.status === "ok") {
    const saved = await writeUsersCache(cacheFile, result.users);
    return {
      status: "ok",
      users: result.users,
      cache: cached ? "miss_stale_refreshed" : "miss_empty_refreshed",
      updatedAt: saved.updatedAt
    };
  }

  if (result.status === "not_configured") {
    if (cached) {
      return { status: "ok", users: cached.users, cache: "stale_fallback_not_configured", updatedAt: cached.updatedAt };
    }
    return { status: "not_configured", users: [] };
  }

  logger.warn?.("[usersCache] refresh failed, fallback to cache when possible");
  if (cached) {
    return { status: "ok", users: cached.users, cache: "stale_fallback_error", updatedAt: cached.updatedAt };
  }
  return { status: "error", users: [], error: result.error || "cache_refresh_failed" };
}

export async function forceRefreshUsersCache({ cacheFile, provider }) {
  const result = await provider.listActiveUsers();
  if (result.status !== "ok") return result;
  const saved = await writeUsersCache(cacheFile, result.users);
  return { status: "ok", users: result.users, updatedAt: saved.updatedAt };
}
