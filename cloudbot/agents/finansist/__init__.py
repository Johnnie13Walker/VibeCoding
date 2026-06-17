"""Compatibility layer for the moved Finance agent.

The canonical implementation lives in apps.finansist.
Keep this package until all legacy imports are retired.
"""

from apps.finansist import *  # noqa: F401,F403
