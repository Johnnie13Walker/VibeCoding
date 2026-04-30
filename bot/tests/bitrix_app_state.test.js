import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createBitrixUsersProvider } from "../src/providers/bitrixUsersProvider.js";

async function main() {
  const tmpDir = await mkdtemp(path.join(os.tmpdir(), "bitrix-app-state-"));
  const stateFile = path.join(tmpDir, "install.latest.json");
  const originalFetch = globalThis.fetch;

  try {
    await writeFile(
      stateFile,
      JSON.stringify(
        {
          saved_at: "2026-03-22T08:00:00+03:00",
          payload: {
            "auth[access_token]": "expired-token",
            "auth[refresh_token]": "refresh-token-1",
            "auth[client_endpoint]": "https://portal/rest",
            "auth[server_endpoint]": "https://oauth.bitrix24.tech/rest/",
            "auth[domain]": "portal.bitrix24.ru"
          }
        },
        null,
        2
      ),
      "utf-8"
    );

    globalThis.fetch = async (url, options = {}) => {
      const body = String(options.body || "");
      if (String(url).endsWith("/user.get.json")) {
        if (body.includes("auth=expired-token")) {
          return {
            ok: false,
            status: 401,
            async json() {
              return {
                error: "expired_token",
                error_description: "The access token provided has expired"
              };
            }
          };
        }
        if (body.includes("auth=fresh-token")) {
          return {
            ok: true,
            status: 200,
            async json() {
              return {
                result: [
                  { ID: "1", NAME: "Иван", LAST_NAME: "Иванов", ACTIVE: "Y" },
                  { ID: "2", NAME: "Уволенный", LAST_NAME: "Сотрудник", ACTIVE: "N" }
                ]
              };
            }
          };
        }
      }

      if (String(url).endsWith("/oauth/token/")) {
        return {
          ok: true,
          status: 200,
          async json() {
            return {
              access_token: "fresh-token",
              refresh_token: "refresh-token-2",
              client_endpoint: "https://portal/rest",
              server_endpoint: "https://oauth.bitrix24.tech/rest/",
              domain: "portal.bitrix24.ru"
            };
          }
        };
      }

      throw new Error(`Unexpected url: ${url}`);
    };

    const provider = createBitrixUsersProvider({
      config: {
        useFixtureUsers: false,
        bitrixAppStateDir: tmpDir,
        bitrixAppInstallStateFile: "",
        bitrixClientId: "local.app",
        bitrixClientSecret: "secret",
        bitrixOauthTokenUrl: "https://oauth.bitrix24.tech/oauth/token/",
        bitrixTimeoutMs: 1000
      },
      logger: console
    });

    const result = await provider.listActiveUsers();
    assert.equal(result.status, "ok");
    assert.equal(result.source, "bitrix_app");
    assert.equal(result.users.length, 1);
    assert.equal(String(result.users[0].id), "1");

    const saved = JSON.parse(await readFile(stateFile, "utf-8"));
    assert.equal(saved.payload["auth[access_token]"], "fresh-token");
    assert.equal(saved.payload["auth[refresh_token]"], "refresh-token-2");

    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      async json() {
        return {
          error: "INVALID_CREDENTIALS",
          error_description: "Invalid webhook token"
        };
      }
    });

    const webhookProvider = createBitrixUsersProvider({
      config: {
        useFixtureUsers: false,
        bitrixWebhookUrl: "https://portal/rest/1/broken",
        bitrixTimeoutMs: 1000
      },
      logger: { error() {} }
    });

    const webhookResult = await webhookProvider.listActiveUsers();
    assert.equal(webhookResult.status, "error");
    assert.match(webhookResult.error, /Invalid webhook token/);

    console.log("BITRIX APP STATE OK");
  } finally {
    globalThis.fetch = originalFetch;
    await rm(tmpDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error("BITRIX APP STATE FAIL", error);
  process.exit(1);
});
