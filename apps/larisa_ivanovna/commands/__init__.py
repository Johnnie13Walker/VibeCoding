"""Registry команд Ларисы Ивановны."""

from .get_content_topics import build_command as build_get_content_topics_command
from .get_content_post import build_command as build_get_content_post_command
from .get_day_brief import build_command as build_get_day_brief_command
from .get_meetings import build_command as build_get_meetings_command
from .get_midday_replan import build_command as build_get_midday_replan_command
from .get_tasks import build_command as build_get_tasks_command
from .get_weather import build_command as build_get_weather_command
from .get_web_search import build_command as build_get_web_search_command
from .plan_day import build_command as build_plan_day_command

__all__ = [
    "build_get_content_topics_command",
    "build_get_content_post_command",
    "build_get_day_brief_command",
    "build_get_meetings_command",
    "build_get_midday_replan_command",
    "build_get_tasks_command",
    "build_get_weather_command",
    "build_get_web_search_command",
    "build_plan_day_command",
]
