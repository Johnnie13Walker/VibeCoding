import { LARISA_COMMAND_ALIASES } from "../config";
import { runWeatherWorkflow, type WeatherWorkflowDeps } from "../workflows/weather.workflow";

export function createGetWeatherCommand(deps: WeatherWorkflowDeps) {
  return {
    name: "get_weather",
    aliases: LARISA_COMMAND_ALIASES.getWeather,
    async execute(input: { dateMsk: string; city?: string }) {
      const result = await runWeatherWorkflow(input, deps);

      return {
        text: result.text,
        payload: result,
      };
    },
  };
}
