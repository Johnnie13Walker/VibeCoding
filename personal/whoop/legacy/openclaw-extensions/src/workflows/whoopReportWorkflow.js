import { discoverWhoopData, runWhoopDailyReport, runWhoopTelegramTest } from '../services/whoopReporter.js';

function compact(text, max = 900) {
  const t = String(text || '').trim();
  if (!t) return '';
  return t.length > max ? `${t.slice(0, max)}...` : t;
}

function formatResult(title, result) {
  const lines = [title, `Статус: ${result.ok ? 'ОК' : 'есть проблемы'}`, `Деталь: ${result.message}`];
  const stderr = compact(result.stderr || '');
  const stdout = compact(result.stdout || '');
  if (stderr) lines.push('', 'stderr:', stderr);
  if (stdout) lines.push('', 'stdout:', stdout);
  return lines.join('\n');
}

const whoopReportWorkflow = {
  async run(_input, context = {}) {
    const mode = String(context.arg || '').trim().toLowerCase();
    if (mode === 'discover' || mode === 'discovery') {
      const result = await discoverWhoopData(context);
      const data = result.data || {};
      const tg = data.telegram || {};
      const wp = data.whoop || {};
      const env = data.env || {};

      const lines = [
        'WHOOP: discovery',
        `Статус: ${result.ok ? 'ОК' : 'есть проблемы'}`,
        `Деталь: ${result.message}`,
        '',
        'ENV:',
        `- WHOOP_CLIENT_ID: ${env.WHOOP_CLIENT_ID ? 'есть' : 'нет'}`,
        `- WHOOP_CLIENT_SECRET: ${env.WHOOP_CLIENT_SECRET ? 'есть' : 'нет'}`,
        `- WHOOP_REFRESH_TOKEN: ${env.WHOOP_REFRESH_TOKEN ? 'есть' : 'нет'}`,
        `- WHOOP_REDIRECT_URI: ${env.WHOOP_REDIRECT_URI ? 'есть' : 'нет'}`,
        `- TELEGRAM_BOT_TOKEN: ${env.TELEGRAM_BOT_TOKEN ? 'есть' : 'нет'}`,
        `- TELEGRAM_CHAT_ID: ${env.TELEGRAM_CHAT_ID ? 'есть' : 'нет'}`,
        '',
        'Telegram:',
        `- getMe: ${tg.getMeOk ? 'ok' : 'ошибка'}`,
        `- getUpdates count: ${tg.updatesCount || 0}`,
        `- configured chat_id: ${tg.configuredChatId || 'нет'}`,
        `- configured chat send: ${tg.sendTestToConfiguredChat ? (tg.sendTestToConfiguredChat.ok ? 'ok' : `ошибка (${tg.sendTestToConfiguredChat.description || 'unknown'})`) : 'не проверено'}`,
        `- chat candidates: ${(tg.chatCandidates || []).map((x) => x.id).join(', ') || 'нет'}`,
        '',
        'WHOOP:',
        `- auth url: ${wp.authUrl || 'нет'}`,
        `- dry-run: ${wp.dryRunOk ? 'ok' : 'ошибка'}`,
        ...(wp.dryRunError ? ['', 'dry-run error:', String(wp.dryRunError).slice(0, 1200)] : []),
      ];

      return {
        response: { text: lines.join('\n') },
        nextState: null,
      };
    }
    if (mode === 'test' || mode === 'telegram-test') {
      const result = await runWhoopTelegramTest(context);
      return {
        response: { text: formatResult('WHOOP: тест Telegram', result) },
        nextState: null,
      };
    }

    const dryRun = mode.includes('dry') || mode.includes('preview');
    const force = mode.includes('force');
    const result = await runWhoopDailyReport(context, { dryRun, force });
    return {
      response: { text: formatResult('WHOOP: ежедневный отчет', result) },
      nextState: null,
    };
  },

  async continue(_state, input, context = {}) {
    return this.run(input, context);
  },
};

export { whoopReportWorkflow };
