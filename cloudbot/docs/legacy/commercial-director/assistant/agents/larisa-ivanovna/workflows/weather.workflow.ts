import { formatTelegramWeather } from "../formatters/telegramWeather.formatter";
import { LARISA_IVANOVNA_TIMEZONE, larisaIvanovnaConfig } from "../config";
import type { WeatherSnapshot } from "../schemas/brief.schema";
import type { WeatherProvider } from "../providers/weather.provider";

export interface WeatherWorkflowDeps {
  weatherProvider: WeatherProvider;
}

export interface WeatherWorkflowResult {
  text: string;
  weather: WeatherSnapshot;
}

export async function runWeatherWorkflow(
  input: { dateMsk: string; city?: string },
  deps: WeatherWorkflowDeps,
): Promise<WeatherWorkflowResult> {
  const weather = await deps.weatherProvider.getWeather({
    dateMsk: input.dateMsk,
    city: input.city ?? larisaIvanovnaConfig.defaultCity,
    timezone: LARISA_IVANOVNA_TIMEZONE,
  });

  return {
    text: formatTelegramWeather(weather),
    weather,
  };
}
