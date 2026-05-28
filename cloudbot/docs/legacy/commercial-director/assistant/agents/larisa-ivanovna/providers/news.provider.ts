import { LARISA_IVANOVNA_TIMEZONE } from "../config";
import type { NewsDigest } from "../schemas/news.schema";

export interface NewsDigestQuery {
  dateMsk: string;
  topics: readonly string[];
  timezone: typeof LARISA_IVANOVNA_TIMEZONE;
}

export interface NewsProvider {
  readonly providerId?: string;
  getDigest(input: NewsDigestQuery): Promise<NewsDigest>;
}

export class NullNewsProvider implements NewsProvider {
  readonly providerId = "null-news";

  async getDigest(input: NewsDigestQuery): Promise<NewsDigest> {
    return {
      dateMsk: input.dateMsk,
      topics: input.topics,
      items: [],
      sourceAvailable: false,
      limitation: "News provider не подключен. Темы можно зафиксировать позже.",
    };
  }
}
