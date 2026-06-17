import { LARISA_IVANOVNA_TIMEZONE } from "../config";
import type { SearchProvider, SearchResponse } from "../providers/search.provider";

export interface SearchWorkflowDeps {
  searchProvider: SearchProvider;
}

export interface SearchWorkflowResult {
  text: string;
  response: SearchResponse;
}

export async function runSearchWorkflow(
  input: { query: string },
  deps: SearchWorkflowDeps,
): Promise<SearchWorkflowResult> {
  const response = await deps.searchProvider.search({
    query: input.query,
    timezone: LARISA_IVANOVNA_TIMEZONE,
  });

  if (!response.sourceAvailable) {
    return {
      text: response.limitation ?? "Поиск сейчас недоступен.",
      response,
    };
  }

  if (response.results.length === 0) {
    return {
      text: "По запросу не найдено подтвержденных результатов.",
      response,
    };
  }

  const lines = response.results.slice(0, 5).map((result) => {
    const urlPart = result.url === undefined ? "" : ` — ${result.url}`;
    return `- ${result.title}${urlPart}`;
  });

  return {
    text: [`Результаты поиска по запросу: ${response.query}`, ...lines].join("\n"),
    response,
  };
}
