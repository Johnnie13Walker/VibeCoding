import { readJsonFile, writeJsonFile } from "./jsonFileStore.js";

const DEFAULT_TTL_MS = 7 * 24 * 60 * 60 * 1000;

function emptyState() {
  return { entries: [] };
}

export function createNotificationLogStore({ filePath, ttlMs = DEFAULT_TTL_MS }) {
  async function load() {
    const state = await readJsonFile(filePath, emptyState());
    if (!state || typeof state !== "object" || !Array.isArray(state.entries)) {
      return emptyState();
    }
    return state;
  }

  async function save(state) {
    await writeJsonFile(filePath, state);
  }

  async function cleanup(nowTs = Date.now()) {
    const state = await load();
    const minTs = nowTs - ttlMs;
    const filtered = state.entries.filter(
      (entry) => Number.isFinite(entry?.sentAt) && entry.sentAt >= minTs
    );

    if (filtered.length !== state.entries.length) {
      state.entries = filtered;
      await save(state);
    }
    return state;
  }

  return {
    async wasSent(key, nowTs = Date.now()) {
      const state = await cleanup(nowTs);
      return state.entries.some((entry) => entry.key === key);
    },

    async markSent({ key, sentAt = Date.now(), payload = null }) {
      const state = await cleanup(sentAt);
      state.entries.push({ key, sentAt, payload });
      await save(state);
    }
  };
}
