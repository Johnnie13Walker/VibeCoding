"""Provider contracts и адаптеры Ларисы Ивановны."""

from .calendar_provider import BitrixCalendarProvider, CalendarProvider, NullCalendarProvider
from .tasks_provider import NullTasksProvider, TasksProvider, TodoistTasksProvider
from .telegram_provider import NullTelegramProvider, SharedTelegramRouteProvider, TelegramProvider
from .weather_provider import NullWeatherProvider, OpenMeteoWeatherProvider, WeatherProvider

__all__ = [
    "BitrixCalendarProvider",
    "CalendarProvider",
    "NullCalendarProvider",
    "NullTasksProvider",
    "NullTelegramProvider",
    "NullWeatherProvider",
    "OpenMeteoWeatherProvider",
    "SharedTelegramRouteProvider",
    "TasksProvider",
    "TelegramProvider",
    "TodoistTasksProvider",
    "WeatherProvider",
]
