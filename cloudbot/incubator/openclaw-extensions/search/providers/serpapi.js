import { requestJson } from './http.js';

function timeRangeToTbs(timeRange) {
  if (!timeRange) return undefined;
  const map = { day: 'd', week: 'w', month: 'm', year: 'y' };
  const qdr = map[timeRange];
  return qdr ? `qdr:${qdr}` : undefined;
}

export async function searchWithSerpApi(query, opts = {}) {
  const apiKey = process.env.SERPAPI_API_KEY;
  if (!apiKey) {
    throw { code: 'missing_key', message: 'SERPAPI_API_KEY is not set', retryable: false };
  }

  const params = new URLSearchParams({
    engine: 'google',
    q: query,
    api_key: apiKey,
    num: String(Number.isFinite(opts.numResults) ? Math.min(Math.max(opts.numResults, 1), 20) : 10),
  });

  const tbs = timeRangeToTbs(opts.timeRange);
  if (tbs) params.set('tbs', tbs);
  if (opts.lang) params.set('hl', opts.lang);

  const { data } = await requestJson(`https://serpapi.com/search.json?${params.toString()}`);

  const organic = Array.isArray(data?.organic_results) ? data.organic_results : [];
  const answer = data?.answer_box?.answer || data?.answer_box?.snippet || data?.knowledge_graph?.description;

  const results = organic
    .map((item) => ({
      title: item?.title || item?.link || 'Untitled',
      url: item?.link || '',
      snippet: item?.snippet,
      source: item?.source,
    }))
    .filter((item) => item.url);

  return {
    provider: 'serpapi',
    query,
    results,
    answer,
    raw: data,
  };
}
