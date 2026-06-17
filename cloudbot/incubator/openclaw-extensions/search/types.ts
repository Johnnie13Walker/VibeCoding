export type SearchProvider = 'serper' | 'serpapi' | 'ddg';

export type SearchTimeRange = 'day' | 'week' | 'month' | 'year';

export interface SearchOptions {
  numResults?: number;
  timeRange?: SearchTimeRange;
  lang?: string;
}

export interface SearchResultItem {
  title: string;
  url: string;
  snippet?: string;
  source?: string;
}

export interface SearchResponse {
  provider: SearchProvider;
  query: string;
  results: SearchResultItem[];
  answer?: string;
  raw?: any;
}
