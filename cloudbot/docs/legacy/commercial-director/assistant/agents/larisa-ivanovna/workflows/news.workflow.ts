import { formatTelegramNewsDigest } from "../formatters/telegramNews.formatter";
import { LARISA_IVANOVNA_TIMEZONE, larisaIvanovnaConfig } from "../config";
import type { NewsDigest } from "../schemas/news.schema";
import type { NewsProvider } from "../providers/news.provider";

export interface NewsWorkflowDeps {
  newsProvider: NewsProvider;
}

export interface NewsWorkflowResult {
  text: string;
  digest: NewsDigest;
}

export async function runNewsWorkflow(
  input: { dateMsk: string; topics?: string[] },
  deps: NewsWorkflowDeps,
): Promise<NewsWorkflowResult> {
  const topics = input.topics ?? [...larisaIvanovnaConfig.defaultNewsTopics];

  const digest = await deps.newsProvider.getDigest({
    dateMsk: input.dateMsk,
    topics,
    timezone: LARISA_IVANOVNA_TIMEZONE,
  });

  return {
    text: formatTelegramNewsDigest(digest),
    digest,
  };
}
