import { LARISA_IVANOVNA_TIMEZONE } from "../config";

export interface SearchResult {
  title: string;
  url?: string;
  snippet: string;
  source: string;
}

export interface SearchQuery {
  query: string;
  timezone: typeof LARISA_IVANOVNA_TIMEZONE;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  sourceAvailable: boolean;
  limitation?: string;
}

export interface SearchProvider {
  readonly providerId?: string;
  search(input: SearchQuery): Promise<SearchResponse>;
}

export class NullSearchProvider implements SearchProvider {
  readonly providerId = "null-search";

  async search(input: SearchQuery): Promise<SearchResponse> {
    return {
      query: input.query,
      results: [],
      sourceAvailable: false,
      limitation: "Search provider не подключен к агенту Ларисы Ивановны.",
    };
  }
}
