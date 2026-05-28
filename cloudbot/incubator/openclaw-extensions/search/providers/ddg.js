import { requestJson } from './http.js';

function collectRelatedTopics(topics, acc) {
  for (const item of topics || []) {
    if (item?.FirstURL) {
      acc.push({
        title: item?.Text?.split(' - ')[0] || item?.FirstURL,
        url: item?.FirstURL,
        snippet: item?.Text,
        source: 'DuckDuckGo',
      });
      continue;
    }
    if (Array.isArray(item?.Topics)) collectRelatedTopics(item.Topics, acc);
  }
}

export async function searchWithDdg(query, opts = {}) {
  const params = new URLSearchParams({
    q: query,
    format: 'json',
    no_html: '1',
    skip_disambig: '1',
  });

  if (opts.lang) params.set('kl', opts.lang);

  const { data } = await requestJson(`https://api.duckduckgo.com/?${params.toString()}`);

  const results = [];

  if (data?.AbstractURL) {
    results.push({
      title: data?.Heading || data?.AbstractSource || 'Instant Answer',
      url: data?.AbstractURL,
      snippet: data?.AbstractText,
      source: data?.AbstractSource || 'DuckDuckGo',
    });
  }

  if (Array.isArray(data?.Results)) {
    for (const item of data.Results) {
      if (!item?.FirstURL) continue;
      results.push({
        title: item?.Text?.split(' - ')[0] || item?.FirstURL,
        url: item?.FirstURL,
        snippet: item?.Text,
        source: 'DuckDuckGo',
      });
    }
  }

  if (Array.isArray(data?.RelatedTopics)) {
    collectRelatedTopics(data.RelatedTopics, results);
  }

  const unique = [];
  const seen = new Set();
  for (const item of results) {
    if (!item.url || seen.has(item.url)) continue;
    seen.add(item.url);
    unique.push(item);
  }

  const limit = Number.isFinite(opts.numResults) ? Math.max(opts.numResults, 1) : 10;

  return {
    provider: 'ddg',
    query,
    results: unique.slice(0, limit),
    answer: data?.AbstractText || undefined,
    raw: data,
  };
}
