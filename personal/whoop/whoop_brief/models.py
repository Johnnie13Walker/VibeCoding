from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DailyMetrics:
    date: str
    recovery: Optional[float] = None
    hrv_ms: Optional[float] = None
    rhr_bpm: Optional[float] = None
    spo2_pct: Optional[float] = None
    sleep_minutes: Optional[int] = None
    sleep_need_minutes: Optional[int] = None
    sleep_performance_pct: Optional[float] = None
    sleep_efficiency_pct: Optional[float] = None
    strain: Optional[float] = None


@dataclass(frozen=True)
class Baseline30d:
    sample_count: int
    recovery: Optional[float] = None
    hrv_ms: Optional[float] = None
    rhr_bpm: Optional[float] = None
    sleep_minutes: Optional[int] = None
    sleep_efficiency_pct: Optional[float] = None

    @property
    def incomplete(self) -> bool:
        return self.sample_count < 30


@dataclass(frozen=True)
class Streak:
    name: str
    days: int = 0


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str
    emoji: str
    text: str
    streak_days: int = 0
    doctor_hint: bool = False
    value: Optional[str] = None  # подстрока в text для bold-выделения в renderer


@dataclass(frozen=True)
class TrainingPlan:
    duration: str
    hr_zone: str
    modality: str
    steps_target: str
    sleep_action: str


@dataclass(frozen=True)
class Verdict:
    color: str
    emoji: str
    headline: str
    top_flag: str
    flags: list[Flag] = field(default_factory=list)
    plan: TrainingPlan = field(default_factory=lambda: TrainingPlan("", "", "", "", ""))

