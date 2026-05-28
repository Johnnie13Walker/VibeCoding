import type { NewsDigest } from "../schemas/news.schema";

export function formatTelegramNewsDigest(digest: NewsDigest): string {
  if (!digest.sourceAvailable) {
    return digest.limitation ?? "Новостной источник недоступен.";
  }

  if (digest.items.length === 0) {
    return "По подтвержденным темам новостей пока нет.";
  }

  return digest.items
    .map((item) => {
      const linkPart = item.url === undefined ? "" : ` — ${item.url}`;
      return `- ${item.topic}: ${item.title}${linkPart}`;
    })
    .join("\n");
}
