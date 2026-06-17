import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const DEFAULT_WHOOP_DIR = '/Users/pro2kuror/Desktop/VibeCoding/personal/whoop';
const DEFAULT_TZ = 'Europe/Moscow';

function envMap(context = {}) {
  return { ...process.env, ...(context.env || {}) };
}

function resolveWhoop(context = {}) {
  const env = envMap(context);
  const whoopDir = String(env.WHOOP_PROJECT_DIR || DEFAULT_WHOOP_DIR).trim();
  const scriptPath = String(env.WHOOP_REPORT_SCRIPT || `${whoopDir}/scripts/whoop_telegram_report.py`).trim();
  return { whoopDir, scriptPath };
}

function parseEnvFileText(raw) {
  const out = {};
  for (const lineRaw of String(raw || '').split(/\r?\n/)) {
    const line = lineRaw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const idx = line.indexOf('=');
    const key = line.slice(0, idx).trim();
    const value = line.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '');
    if (key) out[key] = value;
  }
  return out;
}

async function readEnvFile(envPath) {
  const { stdout } = await execFileAsync('cat', [envPath], { encoding: 'utf8' });
  return parseEnvFileText(stdout);
}

export async function runWhoopDailyReport(context = {}, options = {}) {
  const { whoopDir, scriptPath } = resolveWhoop(context);
  if (!existsSync(scriptPath)) {
    return { ok: false, message: `Не найден WHOOP-скрипт: ${scriptPath}`, stdout: '', stderr: '' };
  }

  const args = [scriptPath, 'send-report'];
  if (options.dryRun) args.push('--dry-run');
  if (options.force) args.push('--force');

  const env = {
    ...envMap(context),
    TZ: String((context.env || {}).TZ || process.env.TZ || DEFAULT_TZ),
  };

  try {
    const { stdout, stderr } = await execFileAsync('python3', args, {
      cwd: whoopDir,
      env,
      encoding: 'utf8',
      timeout: 120000,
      maxBuffer: 2 * 1024 * 1024,
    });
    return { ok: true, message: 'WHOOP-отчет выполнен', stdout: stdout || '', stderr: stderr || '' };
  } catch (err) {
    return {
      ok: false,
      message: `WHOOP-отчет завершился ошибкой: ${String(err?.message || err)}`,
      stdout: String(err?.stdout || ''),
      stderr: String(err?.stderr || ''),
    };
  }
}

export async function runWhoopTelegramTest(context = {}) {
  const { whoopDir } = resolveWhoop(context);
  const envPath = String((context.env || {}).WHOOP_ENV_FILE || `${whoopDir}/.env`).trim();

  if (!existsSync(envPath)) {
    return { ok: false, message: `Не найден env файл WHOOP: ${envPath}` };
  }

  let envFile;
  try {
    envFile = await readEnvFile(envPath);
  } catch (err) {
    return { ok: false, message: `Не удалось прочитать ${envPath}: ${String(err?.message || err)}` };
  }

  const token = String(envFile.TELEGRAM_BOT_TOKEN || '').trim();
  const chatId = String(envFile.TELEGRAM_CHAT_ID || '').trim();
  if (!token || !chatId) {
    return { ok: false, message: 'В WHOOP .env не заданы TELEGRAM_BOT_TOKEN и/или TELEGRAM_CHAT_ID' };
  }

  const now = new Intl.DateTimeFormat('ru-RU', {
    timeZone: 'Europe/Moscow',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).format(new Date());

  const text = `Тест оркестратора WHOOP (${now} МСК): канал доставки работает.`;

  const js = `
const token = process.argv[1];
const chatId = process.argv[2];
const text = process.argv[3];
const url = \`https://api.telegram.org/bot\${token}/sendMessage\`;
const body = new URLSearchParams({ chat_id: chatId, text, parse_mode: 'HTML' });
const res = await fetch(url, { method: 'POST', body });
const json = await res.json();
if (!json.ok) {
  console.error(JSON.stringify(json));
  process.exit(1);
}
console.log(JSON.stringify(json));
`;

  try {
    const { stdout, stderr } = await execFileAsync('node', ['--input-type=module', '-e', js, token, chatId, text], {
      cwd: whoopDir,
      encoding: 'utf8',
      timeout: 30000,
      maxBuffer: 1024 * 1024,
    });
    return { ok: true, message: 'Тестовое сообщение в Telegram отправлено', stdout: stdout || '', stderr: stderr || '' };
  } catch (err) {
    return {
      ok: false,
      message: `Тестовая отправка в Telegram не удалась: ${String(err?.message || err)}`,
      stdout: String(err?.stdout || ''),
      stderr: String(err?.stderr || ''),
    };
  }
}


export async function discoverWhoopData(context = {}) {
  const { whoopDir, scriptPath } = resolveWhoop(context);
  const envPath = String((context.env || {}).WHOOP_ENV_FILE || `${whoopDir}/.env`).trim();

  const out = {
    whoopDir,
    scriptPath,
    envPath,
    env: {
      WHOOP_CLIENT_ID: false,
      WHOOP_CLIENT_SECRET: false,
      WHOOP_REFRESH_TOKEN: false,
      WHOOP_REDIRECT_URI: false,
      TELEGRAM_BOT_TOKEN: false,
      TELEGRAM_CHAT_ID: false,
    },
    telegram: {
      getMeOk: false,
      getMe: null,
      updatesCount: 0,
      chatCandidates: [],
      sendTestToConfiguredChat: null,
      configuredChatId: '',
    },
    whoop: {
      authUrl: null,
      dryRunOk: false,
      dryRunError: '',
    },
  };

  if (!existsSync(envPath)) {
    return { ok: false, message: `Не найден env файл WHOOP: ${envPath}`, data: out };
  }

  let envFile;
  try {
    envFile = await readEnvFile(envPath);
  } catch (err) {
    return { ok: false, message: `Не удалось прочитать ${envPath}: ${String(err?.message || err)}`, data: out };
  }

  for (const k of Object.keys(out.env)) {
    out.env[k] = Boolean(String(envFile[k] || '').trim());
  }

  const token = String(envFile.TELEGRAM_BOT_TOKEN || '').trim();
  const configuredChat = String(envFile.TELEGRAM_CHAT_ID || '').trim();
  out.telegram.configuredChatId = configuredChat;

  if (token) {
    try {
      const meRes = await fetch(`https://api.telegram.org/bot${token}/getMe`);
      const meJson = await meRes.json();
      out.telegram.getMeOk = Boolean(meJson?.ok);
      out.telegram.getMe = meJson?.result || null;
    } catch (err) {
      out.telegram.getMeOk = false;
    }

    try {
      const updRes = await fetch(`https://api.telegram.org/bot${token}/getUpdates`);
      const updJson = await updRes.json();
      const result = Array.isArray(updJson?.result) ? updJson.result : [];
      out.telegram.updatesCount = result.length;

      const seen = new Set();
      for (const item of result) {
        const chat = item?.message?.chat || item?.channel_post?.chat || item?.edited_message?.chat;
        if (!chat?.id) continue;
        const id = String(chat.id);
        if (seen.has(id)) continue;
        seen.add(id);
        out.telegram.chatCandidates.push({
          id,
          type: String(chat.type || ''),
          title: String(chat.title || ''),
          username: String(chat.username || ''),
        });
      }
    } catch (err) {
      // ignore
    }

    if (configuredChat) {
      try {
        const body = new URLSearchParams({
          chat_id: configuredChat,
          text: 'Тест проверки chat_id из discovery workflow',
        });
        const sendRes = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, { method: 'POST', body });
        const sendJson = await sendRes.json();
        out.telegram.sendTestToConfiguredChat = {
          ok: Boolean(sendJson?.ok),
          description: String(sendJson?.description || ''),
        };
      } catch (err) {
        out.telegram.sendTestToConfiguredChat = {
          ok: false,
          description: String(err?.message || err),
        };
      }
    }
  }

  if (existsSync(scriptPath)) {
    try {
      const { stdout } = await execFileAsync('python3', [scriptPath, 'auth-url'], {
        cwd: whoopDir,
        env: { ...envMap(context), ...envFile, TZ: DEFAULT_TZ },
        encoding: 'utf8',
        timeout: 60000,
        maxBuffer: 1024 * 1024,
      });
      const m = String(stdout || '').match(/https:\/\/api\.prod\.whoop\.com\/oauth\/oauth2\/auth\S+/);
      out.whoop.authUrl = m ? m[0] : null;
    } catch (err) {
      out.whoop.authUrl = null;
    }

    try {
      await execFileAsync('python3', [scriptPath, 'send-report', '--dry-run', '--force'], {
        cwd: whoopDir,
        env: { ...envMap(context), ...envFile, TZ: DEFAULT_TZ },
        encoding: 'utf8',
        timeout: 120000,
        maxBuffer: 2 * 1024 * 1024,
      });
      out.whoop.dryRunOk = true;
    } catch (err) {
      out.whoop.dryRunOk = false;
      out.whoop.dryRunError = String(err?.stderr || err?.message || err).trim();
    }
  }

  const ok = out.telegram.getMeOk && out.whoop.dryRunOk;
  return {
    ok,
    message: ok ? 'Discovery выполнен, критичных проблем не найдено' : 'Discovery завершен, найдены проблемы в Telegram/WHOOP',
    data: out,
  };
}
