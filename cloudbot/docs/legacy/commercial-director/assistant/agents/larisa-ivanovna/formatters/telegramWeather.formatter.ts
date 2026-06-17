import type { WeatherSnapshot } from "../schemas/brief.schema";

export function formatTelegramWeather(weather: WeatherSnapshot): string {
  if (!weather.sourceAvailable) {
    return weather.limitation ?? "Погодный источник недоступен.";
  }

  const temperature =
    weather.temperatureC === undefined
      ? null
      : `${weather.temperatureC.min}..${weather.temperatureC.max}°C`;

  const parts = [temperature, weather.summary].filter(Boolean);

  if (weather.alerts !== undefined && weather.alerts.length > 0) {
    parts.push(`Важное: ${weather.alerts.join(", ")}`);
  }

  return parts.join(", ");
}
