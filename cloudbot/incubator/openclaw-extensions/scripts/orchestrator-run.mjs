import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import process from 'node:process';
import { routeIncoming } from '../src/orchestrator/router.js';

const execFileAsync = promisify(execFile);
const TZ = 'Europe/Moscow';

async function loadEnv(path) {
  try {
    const { stdout } = await execFileAsync('cat', [path], { encoding: 'utf8' });
    for (const raw of String(stdout || '').split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith('#') || !line.includes('=')) continue;
      const idx = line.indexOf('=');
      const key = line.slice(0, idx).trim();
      const value = line.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '');
      if (key && !process.env[key]) process.env[key] = value;
    }
  } catch {
    // optional
  }
}

function parseArgs(argv) {
  const out = {
    workflow: '',
    arg: '',
    dryRun: false,
    force: false,
  };
  const args = [...argv];
  while (args.length) {
    const a = args.shift();
    if (a === '--dry-run') out.dryRun = true;
    else if (a === '--force') out.force = true;
    else if (a === '--arg') out.arg = String(args.shift() || '');
    else if (!out.workflow) out.workflow = String(a || '');
    else out.arg = [out.arg, a].filter(Boolean).join(' ').trim();
  }
  return out;
}

function mapWorkflowToText(workflow, arg, flags) {
  const a = String(arg || '').trim();
  if (workflow === 'whoop-daily-report-with-steps') {
    const parts = [a, flags.dryRun ? 'dry' : '', flags.force ? 'force' : ''].filter(Boolean).join(' ');
    return `/whoop_report ${parts}`.trim();
  }
  if (workflow === 'whoop-telegram-test') {
    return '/whoop_test';
  }
  if (workflow === 'whoop-discovery') {
    return '/whoop_discovery';
  }
  if (workflow === 'daily-health-check') {
    return '/diag';
  }
  throw new Error(`Неизвестный workflow: ${workflow}`);
}

async function main() {
  await loadEnv('/Users/pro2kuror/Desktop/OpenClo/incubator/openclaw-extensions/.env');
  await loadEnv('/Users/pro2kuror/Desktop/OpenClo/projects/whoop/.env');

  const parsed = parseArgs(process.argv.slice(2));
  if (!parsed.workflow) {
    console.error('Использование: node scripts/orchestrator-run.mjs <workflow> [--arg "..."] [--dry-run] [--force]');
    console.error('Workflow: whoop-daily-report-with-steps | whoop-telegram-test | whoop-discovery | daily-health-check');
    process.exit(2);
  }

  const text = mapWorkflowToText(parsed.workflow, parsed.arg, parsed);
  const result = await routeIncoming(
    {
      text,
      userId: String(process.env.TELEGRAM_OWNER_ID || 'orchestrator'),
      chatId: String(process.env.TELEGRAM_CHAT_ID || process.env.TELEGRAM_OWNER_ID || 'orchestrator'),
      timezone: TZ,
      metadata: { channel: 'cli' },
    },
    {
      env: { ...process.env, TZ },
    },
  );

  if (!result?.handled) {
    console.error('Workflow не обработан.');
    process.exit(1);
  }

  console.log(result.reply || 'Пустой ответ');
  process.exit(0);
}

main().catch((err) => {
  console.error(`Ошибка orchestrator-run: ${String(err?.message || err)}`);
  process.exit(1);
});
