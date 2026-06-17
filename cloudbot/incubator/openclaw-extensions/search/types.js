/**
 * @typedef {'day'|'week'|'month'|'year'} SearchTimeRange
 */

/**
 * @typedef {Object} SearchOptions
 * @property {number} [numResults]
 * @property {SearchTimeRange} [timeRange]
 * @property {string} [lang]
 */

/**
 * @typedef {Object} SearchResultItem
 * @property {string} title
 * @property {string} url
 * @property {string} [snippet]
 * @property {string} [source]
 */

/**
 * @typedef {'serper'|'serpapi'|'ddg'} SearchProvider
 */

/**
 * @typedef {Object} SearchResponse
 * @property {SearchProvider} provider
 * @property {string} query
 * @property {SearchResultItem[]} results
 * @property {string} [answer]
 * @property {any} [raw]
 */

export {};
