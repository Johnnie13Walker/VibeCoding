import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(MODULE_DIR, "..", "..", "..");

function runSelfHealingProcess(env, logger = console) {
  const pythonBin = String(env.SELF_HEALING_PYTHON_BIN || "python3").trim();

  return new Promise((resolve, reject) => {
    const child = spawn(
      pythonBin,
      ["-m", "cloudbot.devops.self_healing", "--json"],
      {
        cwd: REPO_ROOT,
        env: { ...process.env, ...env },
        stdio: ["ignore", "pipe", "pipe"]
      }
    );

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", (error) => {
      reject(error);
    });
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error((stderr || stdout || `self-healing exit=${code}`).trim()));
        return;
      }

      try {
        resolve(JSON.parse(String(stdout || "{}").trim()));
      } catch (error) {
        logger.error?.("[self_healing] invalid json", error);
        reject(new Error(`Некорректный JSON self-healing: ${stdout}`));
      }
    });
  });
}

export function createSelfHealingJob({
  env = process.env,
  logger = console
} = {}) {
  return {
    name: "self_healing",
    schedule: "0 */6 * * *",
    timezone: "Europe/Moscow",

    async run({ userId, chatId, sendMessage }) {
      if (env.SELF_HEALING_SCHEDULE_ENABLED === "0") {
        return { status: "disabled", sent: false };
      }

      const payload = await runSelfHealingProcess(env, logger);
      const text = String(payload?.text || "SELF HEALING REPORT\n\nSelf-healing недоступен.");
      await sendMessage({
        userId,
        chatId,
        text,
        triggerType: "self_healing"
      });

      return {
        status: payload?.ok ? "ok" : "warning",
        sent: true,
        warnings: payload?.warnings || [],
        actions: payload?.actions || []
      };
    }
  };
}
