import { searchWithSerper } from './providers/serper.js';
import { searchWithSerpApi } from './providers/serpapi.js';
import { searchWithDdg } from './providers/ddg.js';

const PROVIDERS = {
  serper: searchWithSerper,
  serpapi: searchWithSerpApi,
  ddg: searchWithDdg,
};

function providerChain() {
  const chain = [];
  if (process.env.SERPER_API_KEY) chain.push('serper');
  if (process.env.SERPAPI_API_KEY) chain.push('serpapi');
  chain.push('ddg');
  return chain;
}

function shouldFallback(err, response) {
  if (err) {
    if (err.code === 'timeout' || err.code === 'network_error') return true;
    if (typeof err.status === 'number') return [401, 403, 429].includes(err.status) || err.status >= 500;
    if (typeof err.code === 'string') {
      return /^http_(401|403|429|5\d\d)$/.test(err.code);
    }
    return false;
  }

  return !response?.results || response.results.length === 0;
}

/**
 * @param {string} query
 * @param {{numResults?: number, timeRange?: 'day'|'week'|'month'|'year', lang?: string}} [opts]
 * @returns {Promise<{provider:'serper'|'serpapi'|'ddg',query:string,results:Array<{title:string,url:string,snippet?:string,source?:string}>,answer?:string,raw?:any}>}
 */
export async function searchWeb(query, opts = {}) {
  const chain = providerChain();
  const attempts = [];

  for (const name of chain) {
    const runProvider = PROVIDERS[name];

    try {
      const response = await runProvider(query, opts);
      if (!response.results?.length) {
        attempts.push({ provider: name, ok: false, reason: 'empty_results' });
        if (name !== chain[chain.length - 1]) continue;
      } else {
        return {
          ...response,
          raw: {
            providerPayload: response.raw,
            diagnostics: { attempts: [...attempts, { provider: name, ok: true }] },
          },
        };
      }

      return {
        provider: response.provider,
        query,
        results: response.results || [],
        answer: response.answer,
        raw: {
          providerPayload: response.raw,
          diagnostics: { attempts },
        },
      };
    } catch (err) {
      const reason = err?.code || err?.message || 'unknown_error';
      attempts.push({ provider: name, ok: false, reason, status: err?.status });
      if (!shouldFallback(err, null)) {
        throw Object.assign(new Error(`Provider ${name} failed: ${reason}`), { cause: err, attempts });
      }
      if (name === chain[chain.length - 1]) {
        throw Object.assign(new Error(`All providers failed for query: ${query}`), { cause: err, attempts });
      }
    }
  }

  throw new Error('No providers available');
}
