import { LARISA_IVANOVNA_TIMEZONE } from "../config";
import type { WeatherSnapshot } from "../schemas/brief.schema";

export interface WeatherQuery {
  dateMsk: string;
  city: string;
  timezone: typeof LARISA_IVANOVNA_TIMEZONE;
}

export interface WeatherProvider {
  readonly providerId?: string;
  getWeather(input: WeatherQuery): Promise<WeatherSnapshot>;
}

export class NullWeatherProvider implements WeatherProvider {
  readonly providerId = "null-weather";

  async getWeather(input: WeatherQuery): Promise<WeatherSnapshot> {
    return {
      city: input.city,
      summary: "Источник погоды не подключен.",
      alerts: [],
      sourceAvailable: false,
      limitation: "Weather provider не подтвержден в этом контуре.",
      source: "weather",
    };
  }
}
