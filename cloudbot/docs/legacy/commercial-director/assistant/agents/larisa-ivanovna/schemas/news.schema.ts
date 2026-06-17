export interface NewsItem {
  id: string;
  topic: string;
  title: string;
  summary?: string;
  url?: string;
  publishedAtMsk?: string;
  sourceName?: string;
  source: "news";
}

export interface NewsDigest {
  dateMsk: string;
  topics: readonly string[];
  items: NewsItem[];
  sourceAvailable: boolean;
  limitation?: string;
}
