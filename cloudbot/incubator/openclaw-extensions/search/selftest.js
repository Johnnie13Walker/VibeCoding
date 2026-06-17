import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import process from 'node:process';
import { searchWeb } from './index.js';

const TEST_QUERIES = [
  'Bitrix24 calendar REST meeting attendees',
  'site:bitrix24.ru calendar.section.get',
  'Serper API free tier',
];

function parseEnvText(text) {
  const parsed = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const idx = line.indexOf('=');
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    parsed[key] = value;
  }
  return parsed;
}

async function loadDotEnvIfPresent() {
  const path = '.env';
  if (!existsSync(path)) return;
  const content = await readFile(path, 'utf8');
  const env = parseEnvText(content);
  for (const [k, v] of Object.entries(env)) {
    if (!(k in process.env)) process.env[k] = v;
  }
}

function explainFallback(result) {
  const attempts = result?.raw?.diagnostics?.attempts || [];
  const failed = attempts.filter((x) => !x.ok);
  if (!failed.length) return;
  console.log('  fallback:');
  for (const item of failed) {
    const reason = item.status ? `${item.reason} (status ${item.status})` : item.reason;
    console.log(`    - ${item.provider}: ${reason}`);
  }
}

function printTopResults(result) {
  const top = result.results.slice(0, 3);
  for (const item of top) {
    console.log(`    - ${item.title} | ${item.url}`);
  }
}

async function main() {
  await loadDotEnvIfPresent();

  const hasSerper = Boolean(process.env.SERPER_API_KEY);
  const hasSerpApi = Boolean(process.env.SERPAPI_API_KEY);

  console.log('=== Search selftest ===');
  console.log(`keys: SERPER_API_KEY=${hasSerper ? 'set' : 'missing'}, SERPAPI_API_KEY=${hasSerpApi ? 'set' : 'missing'}`);

  let success = false;

  for (const query of TEST_QUERIES) {
    console.log(`\nquery: ${query}`);
    try {
      const result = await searchWeb(query, { numResults: 10, lang: 'en' });
      console.log(`  provider: ${result.provider}`);
      console.log(`  results: ${result.results.length}`);
      printTopResults(result);
      explainFallback(result);
      if (result.results.length >= 3) success = true;
    } catch (err) {
      console.log(`  provider: failed`);
      console.log(`  error: ${err?.message || String(err)}`);
      const attempts = err?.attempts || [];
      if (attempts.length) {
        console.log('  fallback:');
        for (const a of attempts) {
          if (a.ok) continue;
          const reason = a.status ? `${a.reason} (status ${a.status})` : a.reason;
          console.log(`    - ${a.provider}: ${reason}`);
        }
      }
    }
  }

  if (!hasSerper) {
    console.log('\nSerper key not found. Как получить ключ за 2 минуты:');
    console.log('1) Откройте https://serper.dev и зарегистрируйтесь (free tier, без карты).');
    console.log('2) Скопируйте API key из dashboard.');
    console.log('3) Добавьте в .env строку: SERPER_API_KEY=ваш_ключ');
    console.log('4) Повторите: npm run selftest');
  }

  if (success) {
    console.log('\nSELFTEST RESULT: PASS (хотя бы один провайдер вернул >=3 результатов)');
    process.exit(0);
  }

  console.log('\nSELFTEST RESULT: FAIL (ни один провайдер не вернул >=3 результатов)');
  process.exit(1);
}

main().catch((err) => {
  console.error('selftest fatal error:', err?.message || err);
  process.exit(1);
});
