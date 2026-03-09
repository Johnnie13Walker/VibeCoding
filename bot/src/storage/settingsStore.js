import { readJsonFile, writeJsonFile } from "./jsonFileStore.js";

function emptyState() {
  return { users: {} };
}

export function createSettingsStore({ filePath }) {
  async function load() {
    const state = await readJsonFile(filePath, emptyState());
    if (!state || typeof state !== "object" || typeof state.users !== "object") {
      return emptyState();
    }
    return state;
  }

  async function save(state) {
    await writeJsonFile(filePath, state);
  }

  return {
    async getUserSettings(userId) {
      const uid = String(userId || "");
      const state = await load();
      const row = state.users[uid] || {};
      return {
        quietMode: Boolean(row.quietMode),
        updatedAt: row.updatedAt || null
      };
    },

    async setQuietMode(userId, enabled) {
      const uid = String(userId || "");
      const state = await load();
      state.users[uid] = {
        ...(state.users[uid] || {}),
        quietMode: Boolean(enabled),
        updatedAt: new Date().toISOString()
      };
      await save(state);
      return this.getUserSettings(uid);
    }
  };
}
