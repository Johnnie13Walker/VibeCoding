import { searchWeb } from '../search/index.js';

export async function handleWebSearchIntent(userQuery) {
  const search = await searchWeb(userQuery, { numResults: 8, lang: 'ru' });

  const userLines = search.results.slice(0, 3).map((r, i) => `${i + 1}. ${r.title}\n${r.url}`);
  const userText = [
    `Провайдер: ${search.provider}`,
    userLines.length ? userLines.join('\n\n') : 'По запросу не найдено ссылок.',
  ].join('\n\n');

  const grounding = search.results.slice(0, 3).map((r) => ({
    title: r.title,
    url: r.url,
    snippet: r.snippet || '',
    source: r.source || search.provider,
  }));

  return {
    text: userText,
    grounding,
    provider: search.provider,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const query = process.argv.slice(2).join(' ').trim() || 'Bitrix24 calendar REST meeting attendees';
  const out = await handleWebSearchIntent(query);
  console.log('=== user response ===');
  console.log(out.text);
  console.log('\n=== grounding ===');
  console.log(JSON.stringify(out.grounding, null, 2));
}
