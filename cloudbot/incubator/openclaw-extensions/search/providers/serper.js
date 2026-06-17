import { requestJson } from './http.js';

function timeRangeToTbs(timeRange) {
  if (!timeRange) return undefined;
  const map = { day: 'd', week: 'w', month: 'm', year: 'y' };
  const qdr = map[timeRange];
  return qdr ? `qdr:${qdr}` : undefined;
}

export async function searchWithSerper(query, opts = {}) {
  const apiKey = process.env.SERPER_API_KEY;
  if (!apiKey) {
    throw { code: 'missing_key', message: 'SERPER_API_KEY is not set', retryable: false };
  }

  const payload = {
    q: query,
    num: Number.isFinite(opts.numResults) ? Math.min(Math.max(opts.numResults, 1), 20) : 10,
  };

  const tbs = timeRangeToTbs(opts.timeRange);
  if (tbs) payload.tbs = tbs;
  if (opts.lang) payload.hl = opts.lang;

  const { data } = await requestJson('https://google.serper.dev/search', {
    method: 'POST',
    headers: {
      'X-API-KEY': apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  const organic = Array.isArray(data?.organic) ? data.organic : [];
  const answer = data?.answerBox?.answer || data?.answerBox?.snippet || data?.knowledgeGraph?.description;

  const results = organic
    .map((item) => ({
      title: item?.title || item?.link || 'Untitled',
      url: item?.link || '',
      snippet: item?.snippet || item?.snippetHighlighted?.join(' '),
      source: item?.source,
    }))
    .filter((item) => item.url);

  return {
    provider: 'serper',
    query,
    results,
    answer,
    raw: data,
  };
}
