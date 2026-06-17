#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import secrets
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from zoneinfo import ZoneInfo


class HttpError(RuntimeError):
    def __init__(self, status: Optional[int], body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


def _load_one_env(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            os.environ.setdefault(key, value)


def load_dotenv_file(path: str = ".env") -> None:
    explicit = os.getenv("WHOOP_ENV_FILE", "").strip()
    if explicit:
        _load_one_env(explicit)
    _load_one_env(path)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_env = os.path.join(os.path.dirname(script_dir), ".env")
    if os.path.abspath(path) != os.path.abspath(project_env):
        _load_one_env(project_env)


def update_env_value(key: str, value: str, path: str = ".env") -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_env = os.path.join(os.path.dirname(script_dir), ".env")
    explicit_target = os.getenv("WHOOP_ENV_FILE", "").strip()
    if explicit_target:
        target = explicit_target
    else:
        target = project_env if os.path.exists(project_env) else path

    lines: List[str] = []
    if os.path.exists(target):
        with open(target, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    prefix = f"{key}="
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")

    with open(target, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def env(name: str, default: Optional[str] = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Не задана переменная окружения: {name}")
    return value or ""


def to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def first_record(payload: Any) -> Optional[Dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("records", "data", "results", "items"):
            maybe = payload.get(key)
            rec = first_record(maybe)
            if rec:
                return rec
        if payload:
            return payload
        return None
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            return first
    return None


def records_list(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("records", "data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        return [payload] if payload else []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def avg(values: List[Optional[float]]) -> Optional[float]:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def format_minutes(minutes: Optional[int]) -> str:
    if minutes is None:
        return "н/д"
    h, m = divmod(minutes, 60)
    return f"{h}ч {m}м"


def format_percent(value: Optional[float], scale_0_1: bool = False) -> str:
    if value is None:
        return "н/д"
    v = value * 100 if scale_0_1 else value
    return f"{v:.0f}%"


def parse_dt(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def record_local_date(record: Dict[str, Any], tz: ZoneInfo) -> Optional[dt.date]:
    for key in ("start", "created_at", "end"):
        d = parse_dt(record.get(key))
        if d is not None:
            return d.astimezone(tz).date()
    return None


def pick_record_for_date(
    records: List[Dict[str, Any]],
    target_date: dt.date,
    tz: ZoneInfo,
    allow_fallback: bool = True,
) -> Optional[Dict[str, Any]]:
    for rec in records:
        rdate = record_local_date(rec, tz)
        if rdate == target_date:
            return rec
    return (records[0] if records else None) if allow_fallback else None


def sparkline(values: List[Optional[float]]) -> str:
    chars = "▁▂▃▄▅▆▇█"
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return "н/д"
    lo, hi = min(nums), max(nums)
    if hi == lo:
        return chars[-1] * len(values)
    out: List[str] = []
    for v in values:
        if v is None:
            out.append("·")
            continue
        idx = int(round((float(v) - lo) / (hi - lo) * (len(chars) - 1)))
        idx = max(0, min(len(chars) - 1, idx))
        out.append(chars[idx])
    return "".join(out)


def series_for_days(
    records: List[Dict[str, Any]],
    extractor,
    *,
    end_date: dt.date,
    days: int,
    tz: ZoneInfo,
) -> List[Optional[float]]:
    by_date: Dict[dt.date, Optional[float]] = {}
    for rec in records:
        d = record_local_date(rec, tz)
        if d is None:
            continue
        if d in by_date:
            continue
        by_date[d] = extractor(rec)
    dates = [end_date - dt.timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    return [by_date.get(d) for d in dates]


def status_emoji(value: Optional[float], *, good_min: Optional[float] = None, bad_max: Optional[float] = None) -> str:
    if value is None:
        return "⚪"
    if good_min is not None and value >= good_min:
        return "🟢"
    if bad_max is not None and value <= bad_max:
        return "🔴"
    return "🟡"


def status_emoji_inverse(value: Optional[float], *, good_max: Optional[float] = None, bad_min: Optional[float] = None) -> str:
    if value is None:
        return "⚪"
    if good_max is not None and value <= good_max:
        return "🟢"
    if bad_min is not None and value >= bad_min:
        return "🔴"
    return "🟡"


def state_file_path() -> str:
    explicit = os.getenv("WHOOP_STATE_FILE", "").strip()
    if explicit:
        return explicit
    env_file = os.getenv("WHOOP_ENV_FILE", "").strip()
    if env_file:
        return os.path.join(os.path.dirname(env_file), "whoop-state.json")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(script_dir), "whoop-state.json")


def load_state() -> Dict[str, Any]:
    path = state_file_path()
    if not os.path.exists(path):
        return {"daily_sent": {}, "weekly_sent": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"daily_sent": {}, "weekly_sent": {}}
        data.setdefault("daily_sent", {})
        data.setdefault("weekly_sent", {})
        return data
    except Exception:
        return {"daily_sent": {}, "weekly_sent": {}}


def save_state(state: Dict[str, Any]) -> None:
    path = state_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def http_json(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    form_body: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Any:
    if json_body is not None and form_body is not None:
        raise ValueError("Передавайте только один тип body: json_body или form_body")

    body_bytes: Optional[bytes] = None
    req_headers: Dict[str, str] = {
        "Accept": "application/json",
        # WHOOP/Cloudflare иногда режет "ботовые" сигнатуры.
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    }
    if headers:
        req_headers.update(headers)

    if json_body is not None:
        body_bytes = json.dumps(json_body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    elif form_body is not None:
        body_bytes = urlencode(form_body).encode("utf-8")
        req_headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = Request(url=url, data=body_bytes, headers=req_headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HttpError(exc.code, body) from exc
    except URLError as exc:
        raise RuntimeError(f"Сетевая ошибка: {exc}") from exc

    if not payload:
        return {}
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Некорректный JSON-ответ: {payload[:300]}") from exc


class WhoopClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, token_url: str, api_base: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_url = token_url
        self.api_base = api_base.rstrip("/")

    def refresh_access_token(self) -> Dict[str, Any]:
        return http_json(
            "POST",
            self.token_url,
            headers={
                "Origin": "https://developer.whoop.com",
                "Referer": "https://developer.whoop.com/",
            },
            form_body={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )

    def get_json(self, access_token: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.api_base}{path}{query}"
        return http_json("GET", url, headers={"Authorization": f"Bearer {access_token}"})


def build_auth_url() -> Dict[str, str]:
    client_id = env("WHOOP_CLIENT_ID", required=True)
    redirect_uri = env("WHOOP_REDIRECT_URI", required=True)
    scope = "offline read:recovery read:sleep read:cycles read:workout"
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
    }
    return {
        "state": state,
        "url": "https://api.prod.whoop.com/oauth/oauth2/auth?" + urlencode(params),
    }


def exchange_code(code: str) -> Dict[str, Any]:
    token_url = env("WHOOP_TOKEN_URL", "https://api.prod.whoop.com/oauth/oauth2/token")
    client_id = env("WHOOP_CLIENT_ID", required=True)
    client_secret = env("WHOOP_CLIENT_SECRET", required=True)
    redirect_uri = env("WHOOP_REDIRECT_URI", required=True)

    return http_json(
        "POST",
        token_url,
        headers={
            "Origin": "https://developer.whoop.com",
            "Referer": "https://developer.whoop.com/",
        },
        form_body={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
    )


def extract_recovery_metrics(recovery: Dict[str, Any]) -> Dict[str, Optional[float]]:
    score_block = recovery.get("score") if isinstance(recovery.get("score"), dict) else {}
    score = to_float(
        recovery.get("recovery_score")
        or score_block.get("recovery_score")
        or recovery.get("score")
    )

    hrv = None
    rhr = None
    spo2 = None
    skin_temp = None
    hrv_keys = ["hrv_rmssd_milli", "hrv_rmssd_ms", "hrv", "hrv_rmssd"]
    rhr_keys = ["resting_heart_rate", "rhr", "resting_heart_rate_bpm"]

    nested_keys = [
        recovery.get("score_state"),
        recovery.get("heart_rate_state"),
        recovery.get("data"),
        score_block,
    ]

    for source in [recovery, *[x for x in nested_keys if isinstance(x, dict)]]:
        if hrv is None:
            for key in hrv_keys:
                hrv = to_float(source.get(key))
                if hrv is not None:
                    break
        if rhr is None:
            for key in rhr_keys:
                rhr = to_float(source.get(key))
                if rhr is not None:
                    break
        if spo2 is None:
            spo2 = to_float(source.get("spo2_percentage"))
        if skin_temp is None:
            skin_temp = to_float(source.get("skin_temp_celsius"))

    return {"score": score, "hrv": hrv, "rhr": rhr, "spo2": spo2, "skin_temp": skin_temp}


def extract_sleep_metrics(sleep: Dict[str, Any]) -> Dict[str, Optional[float]]:
    score_block = sleep.get("score") if isinstance(sleep.get("score"), dict) else {}
    score = to_float(sleep.get("sleep_score") or sleep.get("score"))

    total_min = None
    for key in ("total_sleep_duration_minutes", "total_sleep_time_minutes", "total_in_bed_time_minutes"):
        total_min = to_int(sleep.get(key))
        if total_min is not None:
            break

    if total_min is None:
        for key in ("total_sleep_duration_ms", "total_sleep_duration_milli"):
            ms = to_int(sleep.get(key))
            if ms is not None:
                total_min = int(round(ms / 60000))
                break
    if total_min is None and isinstance(score_block.get("stage_summary"), dict):
        stage = score_block.get("stage_summary") or {}
        sleep_ms = (
            to_int(stage.get("total_light_sleep_time_milli")) or 0
        ) + (
            to_int(stage.get("total_slow_wave_sleep_time_milli")) or 0
        ) + (
            to_int(stage.get("total_rem_sleep_time_milli")) or 0
        )
        if sleep_ms > 0:
            total_min = int(round(sleep_ms / 60000))

    efficiency = None
    for key in ("sleep_efficiency_percentage", "efficiency", "sleep_efficiency"):
        efficiency = to_float(sleep.get(key))
        if efficiency is not None:
            break
    if efficiency is None:
        efficiency = to_float(score_block.get("sleep_efficiency_percentage"))

    performance = to_float(score_block.get("sleep_performance_percentage"))
    consistency = to_float(score_block.get("sleep_consistency_percentage"))
    respiratory_rate = to_float(score_block.get("respiratory_rate"))

    stage = score_block.get("stage_summary") if isinstance(score_block.get("stage_summary"), dict) else {}
    light_min = to_int((to_int(stage.get("total_light_sleep_time_milli")) or 0) / 60000) if stage else None
    deep_min = to_int((to_int(stage.get("total_slow_wave_sleep_time_milli")) or 0) / 60000) if stage else None
    rem_min = to_int((to_int(stage.get("total_rem_sleep_time_milli")) or 0) / 60000) if stage else None

    return {
        "score": score,
        "total_min": total_min,
        "efficiency": efficiency,
        "performance": performance,
        "consistency": consistency,
        "respiratory_rate": respiratory_rate,
        "light_min": light_min,
        "deep_min": deep_min,
        "rem_min": rem_min,
    }


def extract_strain(cycle: Dict[str, Any]) -> Optional[float]:
    score_block = cycle.get("score") if isinstance(cycle.get("score"), dict) else {}
    for key in ("strain", "day_strain", "score"):
        value = to_float(cycle.get(key))
        if value is not None:
            return value
    value = to_float(score_block.get("strain"))
    if value is not None:
        return value
    return None


def load_user_profile() -> Optional[Dict[str, float]]:
    age = to_int(env("USER_AGE_YEARS", ""))
    weight_kg = to_float(env("USER_WEIGHT_KG", ""))
    height_cm = to_float(env("USER_HEIGHT_CM", ""))
    if age is None or weight_kg is None or height_cm is None:
        return None
    if age <= 0 or weight_kg <= 0 or height_cm <= 0:
        return None

    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m * height_m)
    hr_max = max(120, int(round(220 - age)))
    zone2_lo = int(round(hr_max * 0.60))
    zone2_hi = int(round(hr_max * 0.70))
    return {
        "age": float(age),
        "weight_kg": float(weight_kg),
        "height_cm": float(height_cm),
        "bmi": float(bmi),
        "hr_max": float(hr_max),
        "zone2_lo": float(zone2_lo),
        "zone2_hi": float(zone2_hi),
    }


def build_recommendations(
    rec: Dict[str, Optional[float]],
    slp: Dict[str, Optional[float]],
    trend_rhr: Optional[float],
    profile: Optional[Dict[str, float]] = None,
) -> List[str]:
    tips: List[str] = []
    recovery = rec.get("score")
    if recovery is not None:
        if recovery < 35:
            tips.append("Низкое восстановление: сделайте лёгкий день, без интенсивных интервалов.")
        elif recovery < 67:
            tips.append("Среднее восстановление: держите умеренную нагрузку и делайте длинную разминку.")
        else:
            tips.append("Хорошее восстановление: можно планировать интенсивную тренировку.")

    total_sleep = slp.get("total_min")
    if total_sleep is not None and total_sleep < 420:
        tips.append("Сна меньше 7 часов: по возможности добавьте дневной отдых и ложитесь раньше.")

    rhr = rec.get("rhr")
    if rhr is not None and trend_rhr is not None and (rhr - trend_rhr) >= 5:
        tips.append("Пульс в покое выше вашей 7-дневной нормы: снизьте общий объём нагрузки сегодня.")

    if profile is not None:
        bmi = profile["bmi"]
        zone2_lo = int(profile["zone2_lo"])
        zone2_hi = int(profile["zone2_hi"])
        if bmi >= 30:
            tips.append(
                f"С учётом профиля (ИМТ {bmi:.1f}) делайте упор на низкоударную нагрузку: ходьба, эллипс, вело в зоне {zone2_lo}-{zone2_hi} уд/мин."
            )
        else:
            tips.append(
                f"Держите основную аэробную работу в зоне {zone2_lo}-{zone2_hi} уд/мин для устойчивого восстановления."
            )

    if not tips:
        tips.append("Показатели без выраженных отклонений: придерживайтесь обычного плана дня.")
    return tips


def build_plan_b() -> List[str]:
    return [
        "Если утром чувствуете разбитость, тяжесть в ногах или плохой сон по ощущениям:",
        "вместо основной сессии выполните 20-30 минут ходьбы + 15 минут мобилизации + 5 минут дыхания.",
        "Главная цель дня в этом сценарии: восстановиться, а не добрать объём любой ценой.",
    ]


def build_daily_goals(
    slp: Dict[str, Optional[float]],
    day_strain: Optional[float],
    steps_count: Optional[int],
    workouts_count: int,
    profile: Optional[Dict[str, float]] = None,
) -> List[str]:
    goals: List[str] = []

    if day_strain is not None and day_strain >= 12:
        goals.append("Шаги: 5-7 тыс. спокойным темпом (восстановительный день).")
    elif steps_count is not None and steps_count >= 10000:
        goals.append("Шаги: 8-10 тыс. в комфортном темпе.")
    else:
        goals.append("Шаги: 6-8 тыс. спокойным темпом.")

    if profile is not None:
        bmi = profile["bmi"]
        weight_kg = profile["weight_kg"]
        if bmi >= 30:
            goals[0] = "Шаги: 6-8 тыс. без ударной нагрузки (ходьба/дорожка с уклоном), дробно в течение дня."
        base_ml = int(round(weight_kg * 32))
        extra_ml = 500 if workouts_count > 0 or (day_strain is not None and day_strain >= 12) else 0
        total_ml = base_ml + extra_ml
        goals.append(
            f"Вода: {base_ml}-{base_ml + 300} мл базово ({base_ml/1000:.1f}-{(base_ml + 300)/1000:.1f} л) + {extra_ml} мл при тренировке; ориентир ≈ {total_ml/1000:.1f} л."
        )
    else:
        goals.append("Вода: 30-35 мл/кг + электролиты при потливости.")

    goals.append("Питание: обычные порции, без жёсткого дефицита калорий.")

    total_sleep = slp.get("total_min")
    if total_sleep is not None and total_sleep < 420:
        goals.append("Сон: лечь раньше обычного минимум на 30-60 минут.")
    else:
        goals.append("Сон: удержать привычный режим и добавить 20-30 минут запаса ко сну.")

    return goals


def build_alerts(
    rec: Dict[str, Optional[float]],
    slp: Dict[str, Optional[float]],
    trend_rhr: Optional[float],
    trend_resp: Optional[float],
) -> List[str]:
    alerts: List[str] = []
    if rec.get("score") is not None and rec["score"] < 35:
        alerts.append("🔴 Низкое восстановление (ниже 35%). Уберите высокоинтенсивные тренировки.")
    if slp.get("total_min") is not None and slp["total_min"] < 360:
        alerts.append("🟠 Недосып (меньше 6 часов). Сегодня снизьте нагрузку и приоритетно восстановитесь.")
    if rec.get("rhr") is not None and trend_rhr is not None and (rec["rhr"] - trend_rhr) >= 5:
        alerts.append("🟠 Пульс в покое заметно выше 7-дневной нормы.")
    if slp.get("respiratory_rate") is not None and trend_resp is not None and (slp["respiratory_rate"] - trend_resp) >= 1.0:
        alerts.append("🟠 Частота дыхания во сне выше обычной. Следите за самочувствием.")
    if rec.get("spo2") is not None and rec["spo2"] < 94:
        alerts.append("🟠 SpO₂ ниже 94%. Проверьте самочувствие и восстановление.")
    return alerts


def extract_workout_count(workouts_payload: Any) -> int:
    if isinstance(workouts_payload, list):
        return len(workouts_payload)
    if isinstance(workouts_payload, dict):
        for key in ("records", "data", "results", "items"):
            value = workouts_payload.get(key)
            if isinstance(value, list):
                return len(value)
        return 1 if workouts_payload else 0
    return 0


def _collect_step_values(payload: Any) -> List[int]:
    candidates: List[int] = []
    step_keys = {
        "steps",
        "step_count",
        "steps_count",
        "total_steps",
        "daily_steps",
        "distance_walked_steps",
    }

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() in step_keys:
                    step_value = to_int(value)
                    if step_value is not None and step_value >= 0:
                        candidates.append(step_value)
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return candidates


def extract_steps_count(payloads: Sequence[Any]) -> Optional[int]:
    candidates: List[int] = []
    for payload in payloads:
        candidates.extend(_collect_step_values(payload))
    if not candidates:
        return None
    return max(candidates)


def _collect_distance_meters(payload: Any) -> List[float]:
    candidates: List[float] = []
    meter_keys = {
        "distance_meters",
        "distance_meter",
        "distance_m",
    }
    km_keys = {
        "distance_km",
    }

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                kl = key.lower()
                if kl in meter_keys:
                    v = to_float(value)
                    if v is not None and v > 0:
                        candidates.append(v)
                elif kl in km_keys:
                    v = to_float(value)
                    if v is not None and v > 0:
                        candidates.append(v * 1000.0)
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return candidates


def estimate_steps_from_workouts(workouts_payload: Any, stride_meters: float = 0.78) -> Optional[int]:
    distances = _collect_distance_meters(workouts_payload)
    if not distances:
        return None
    if stride_meters <= 0:
        stride_meters = 0.78
    meters_total = max(distances)
    if meters_total <= 0:
        return None
    return int(round(meters_total / stride_meters))


def safe_get_json(client: WhoopClient, access_token: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        return client.get_json(access_token, path, params=params)
    except HttpError as exc:
        if exc.status in (400, 401, 403, 404):
            return None
        raise


def build_report_text(
    tz_name: str,
    report_date: dt.date,
    activity_date: dt.date,
    current_date: dt.date,
    recovery: Optional[Dict[str, Any]],
    sleep: Optional[Dict[str, Any]],
    cycle: Optional[Dict[str, Any]],
    workouts_payload: Any,
    steps_count: Optional[int] = None,
    steps_note: Optional[str] = None,
    profile: Optional[Dict[str, float]] = None,
    lookback_days: int = 1,
    header_note: Optional[str] = None,
    recovery_records: Optional[List[Dict[str, Any]]] = None,
    sleep_records: Optional[List[Dict[str, Any]]] = None,
    cycle_records: Optional[List[Dict[str, Any]]] = None,
) -> str:
    rec = extract_recovery_metrics(recovery or {})
    slp = extract_sleep_metrics(sleep or {})
    day_strain = extract_strain(cycle or {})
    workouts_count = extract_workout_count(workouts_payload)

    recovery_records = recovery_records or []
    sleep_records = sleep_records or []
    cycle_records = cycle_records or []

    rec_last7 = recovery_records[:7]
    trend_recovery_vals = series_for_days(
        rec_last7,
        lambda r: extract_recovery_metrics(r).get("score"),
        end_date=report_date,
        days=7,
        tz=ZoneInfo(tz_name),
    )
    trend_hrv_vals = series_for_days(
        rec_last7,
        lambda r: extract_recovery_metrics(r).get("hrv"),
        end_date=report_date,
        days=7,
        tz=ZoneInfo(tz_name),
    )
    trend_rhr_vals = series_for_days(
        rec_last7,
        lambda r: extract_recovery_metrics(r).get("rhr"),
        end_date=report_date,
        days=7,
        tz=ZoneInfo(tz_name),
    )
    trend_sleep_vals = series_for_days(
        sleep_records[:7],
        lambda r: extract_sleep_metrics(r).get("total_min"),
        end_date=report_date,
        days=7,
        tz=ZoneInfo(tz_name),
    )
    trend_resp_vals = series_for_days(
        sleep_records[:7],
        lambda r: extract_sleep_metrics(r).get("respiratory_rate"),
        end_date=report_date,
        days=7,
        tz=ZoneInfo(tz_name),
    )
    trend_strain_vals = series_for_days(
        cycle_records[:7],
        lambda r: extract_strain(r),
        end_date=report_date,
        days=7,
        tz=ZoneInfo(tz_name),
    )

    trend_recovery = avg(trend_recovery_vals)
    trend_hrv = avg(trend_hrv_vals)
    trend_rhr = avg(trend_rhr_vals)
    trend_sleep = avg(trend_sleep_vals)
    trend_resp = avg(trend_resp_vals)
    trend_strain = avg(trend_strain_vals)

    coach_tips = build_recommendations(rec, slp, trend_rhr, profile=profile)
    alerts = build_alerts(rec, slp, trend_rhr, trend_resp)
    plan_b = build_plan_b()
    goals = build_daily_goals(slp, day_strain, steps_count, workouts_count, profile=profile)

    if activity_date == current_date:
        activity_word = "сегодня"
    elif activity_date == (current_date - dt.timedelta(days=1)):
        activity_word = "вчера"
    else:
        activity_word = activity_date.isoformat()

    e_recovery = status_emoji(rec.get("score"), good_min=67, bad_max=35)
    e_hrv = status_emoji(rec.get("hrv"), good_min=35, bad_max=20)
    e_rhr = status_emoji_inverse(rec.get("rhr"), good_max=70, bad_min=78)
    e_spo2 = status_emoji(rec.get("spo2"), good_min=95, bad_max=93)
    e_skin_temp = "🟡" if rec.get("skin_temp") is not None else "⚪"
    e_sleep_time = status_emoji(slp.get("total_min"), good_min=420, bad_max=360)
    e_sleep_eff = status_emoji(slp.get("efficiency"), good_min=90, bad_max=85)
    e_sleep_perf = status_emoji(slp.get("performance"), good_min=85, bad_max=70)
    e_sleep_cons = status_emoji(slp.get("consistency"), good_min=80, bad_max=60)
    if slp.get("respiratory_rate") is None:
        e_sleep_resp = "⚪"
    elif trend_resp is None:
        e_sleep_resp = status_emoji_inverse(slp.get("respiratory_rate"), good_max=17.0, bad_min=18.5)
    else:
        resp_delta = slp.get("respiratory_rate") - trend_resp
        if resp_delta <= 0.3:
            e_sleep_resp = "🟢"
        elif resp_delta >= 1.0:
            e_sleep_resp = "🔴"
        else:
            e_sleep_resp = "🟡"
    e_strain = status_emoji_inverse(day_strain, good_max=12, bad_min=17)

    lines = [
        f"<b>WHOOP: отчёт за {report_date.isoformat()}</b>",
        *( [f"<i>{header_note}</i>", ""] if header_note else [] ),
        *( [f"<i>Профиль: {int(profile['age'])} лет, {int(round(profile['weight_kg']))} кг, {int(round(profile['height_cm']))} см, ИМТ {profile['bmi']:.1f}.</i>", ""] if profile else [] ),
        "",
        "<b>Сегодняшнее состояние</b>",
        f"• {e_recovery} Восстановление: <b>{format_percent(rec['score'], scale_0_1=False)}</b>",
        f"• {e_hrv} Вариабельность пульса (HRV): <b>{rec['hrv']:.0f} ms</b>" if rec["hrv"] is not None else "• ⚪ Вариабельность пульса (HRV): <b>н/д</b>",
        f"• {e_rhr} Пульс в покое (RHR): <b>{rec['rhr']:.0f} bpm</b>" if rec["rhr"] is not None else "• ⚪ Пульс в покое (RHR): <b>н/д</b>",
        f"• {e_spo2} Кислород в крови (SpO₂): <b>{rec['spo2']:.1f}%</b>" if rec["spo2"] is not None else "• ⚪ Кислород в крови (SpO₂): <b>н/д</b>",
        f"• {e_skin_temp} Температура кожи (не температура тела): <b>{rec['skin_temp']:.1f}°C</b>" if rec["skin_temp"] is not None else "• ⚪ Температура кожи (не температура тела): <b>н/д</b>",
        "",
        "<b>Сон</b>",
        f"• {e_sleep_time} Чистое время сна: <b>{format_minutes(slp['total_min'])}</b>",
        f"• {e_sleep_eff} Эффективность сна: <b>{format_percent(slp['efficiency'], scale_0_1=False)}</b>",
        f"• {e_sleep_perf} Выполнение потребности во сне: <b>{format_percent(slp['performance'], scale_0_1=False)}</b>",
        f"• {e_sleep_cons} Стабильность режима сна: <b>{format_percent(slp['consistency'], scale_0_1=False)}</b>",
        f"• {e_sleep_resp} Частота дыхания во сне: <b>{slp['respiratory_rate']:.1f}/мин</b>" if slp["respiratory_rate"] is not None else "• ⚪ Частота дыхания во сне: <b>н/д</b>",
        f"• Стадии сна (Light/Deep/REM): <b>{format_minutes(slp['light_min'])} / {format_minutes(slp['deep_min'])} / {format_minutes(slp['rem_min'])}</b>",
        "",
        "<b>Нагрузка</b>",
        f"• {e_strain} Дневная нагрузка (strain, {activity_word}): <b>{day_strain:.1f}</b>" if day_strain is not None else f"• ⚪ Дневная нагрузка (strain, {activity_word}): <b>н/д</b>",
        (
            (f"• Шагов {activity_word}: <b>{steps_count:,}</b>".replace(",", " ") + (f" <i>({steps_note})</i>" if steps_note else ""))
            if steps_count is not None
            else f"• Шагов {activity_word}: <b>н/д</b>"
        ),
        f"• Тренировок {activity_word}: <b>{workouts_count}</b>",
        "",
        "<b>Тренд за 7 дней</b>",
        f"• Среднее восстановление: <b>{format_percent(trend_recovery, scale_0_1=False)}</b>",
        f"• Средняя вариабельность пульса (HRV): <b>{trend_hrv:.0f} ms</b>" if trend_hrv is not None else "• Средняя вариабельность пульса (HRV): <b>н/д</b>",
        f"• Средний пульс в покое (RHR): <b>{trend_rhr:.0f} уд/мин</b>" if trend_rhr is not None else "• Средний пульс в покое (RHR): <b>н/д</b>",
        f"• Средний сон: <b>{format_minutes(to_int(trend_sleep) if trend_sleep is not None else None)}</b>",
        f"• Средняя дневная нагрузка: <b>{trend_strain:.1f}</b>" if trend_strain is not None else "• Средняя дневная нагрузка: <b>н/д</b>",
        f"• График восстановления (7д): <b>{sparkline(trend_recovery_vals)}</b>",
        f"• График сна (7д): <b>{sparkline(trend_sleep_vals)}</b>",
        f"• График дневной нагрузки (7д): <b>{sparkline(trend_strain_vals)}</b>",
        "",
        "<b>Алерты</b>",
        *( [f"• {a}" for a in alerts] if alerts else ["• ✅ Критичных сигналов не обнаружено."] ),
        "",
        "<b>Рекомендации тренера на сегодня</b>",
        *[f"• {tip}" for tip in coach_tips],
        "",
        "<b>План Б (если утром самочувствие хуже, чем в отчёте)</b>",
        *[f"• {item}" for item in plan_b],
        "",
        "<b>Цели дня</b>",
        *[f"• {goal}" for goal in goals],
    ]

    return "\n".join(lines)


def build_weekly_report_text(
    tz_name: str,
    week_start: dt.date,
    week_end: dt.date,
    recovery_records: List[Dict[str, Any]],
    sleep_records: List[Dict[str, Any]],
    cycle_records: List[Dict[str, Any]],
    workouts_count: int,
) -> str:
    rec_vals = [extract_recovery_metrics(x).get("score") for x in recovery_records]
    hrv_vals = [extract_recovery_metrics(x).get("hrv") for x in recovery_records]
    rhr_vals = [extract_recovery_metrics(x).get("rhr") for x in recovery_records]
    sleep_vals = [extract_sleep_metrics(x).get("total_min") for x in sleep_records]
    strain_vals = [extract_strain(x) for x in cycle_records]

    best_recovery: Optional[Tuple[dt.date, float]] = None
    worst_recovery: Optional[Tuple[dt.date, float]] = None
    tz = ZoneInfo(tz_name)
    for rec in recovery_records:
        score = extract_recovery_metrics(rec).get("score")
        d = record_local_date(rec, tz)
        if score is None or d is None:
            continue
        if best_recovery is None or score > best_recovery[1]:
            best_recovery = (d, score)
        if worst_recovery is None or score < worst_recovery[1]:
            worst_recovery = (d, score)

    lines = [
        f"<b>WHOOP: недельный отчёт</b>",
        f"<i>{week_start.isoformat()} — {week_end.isoformat()} ({tz_name})</i>",
        "",
        "<b>Средние значения за неделю</b>",
        f"• Восстановление: <b>{format_percent(avg(rec_vals), scale_0_1=False)}</b>",
        f"• HRV: <b>{avg(hrv_vals):.0f} ms</b>" if avg(hrv_vals) is not None else "• HRV: <b>н/д</b>",
        f"• RHR: <b>{avg(rhr_vals):.0f} bpm</b>" if avg(rhr_vals) is not None else "• RHR: <b>н/д</b>",
        f"• Сон: <b>{format_minutes(to_int(avg(sleep_vals)) if avg(sleep_vals) is not None else None)}</b>",
        f"• Strain: <b>{avg(strain_vals):.1f}</b>" if avg(strain_vals) is not None else "• Strain: <b>н/д</b>",
        f"• Тренировок: <b>{workouts_count}</b>",
        "",
        "<b>Динамика</b>",
        f"• Recovery: <b>{sparkline(rec_vals)}</b>",
        f"• Sleep: <b>{sparkline(sleep_vals)}</b>",
        f"• Strain: <b>{sparkline(strain_vals)}</b>",
        "",
        "<b>Лучший / сложный день</b>",
        (
            f"• Лучшее восстановление: <b>{best_recovery[1]:.0f}%</b> ({best_recovery[0].isoformat()})"
            if best_recovery is not None
            else "• Лучшее восстановление: <b>н/д</b>"
        ),
        (
            f"• Самый тяжёлый день по восстановлению: <b>{worst_recovery[1]:.0f}%</b> ({worst_recovery[0].isoformat()})"
            if worst_recovery is not None
            else "• Самый тяжёлый день по восстановлению: <b>н/д</b>"
        ),
    ]
    return "\n".join(lines)


def build_dashboard_chart_url(
    rec: Dict[str, Optional[float]],
    slp: Dict[str, Optional[float]],
    day_strain: Optional[float],
) -> str:
    recovery = rec.get("score") or 0.0
    sleep_eff = slp.get("efficiency") or 0.0
    strain_pct = min(100.0, max(0.0, (day_strain or 0.0) * 5.0))
    hrv_pct = min(100.0, max(0.0, (rec.get("hrv") or 0.0) * 2.0))
    rhr = rec.get("rhr")
    rhr_pct = 0.0 if rhr is None else min(100.0, max(0.0, 100.0 - (rhr - 45.0) * 2.0))

    cfg = {
        "type": "radar",
        "data": {
            "labels": ["Recovery", "Sleep", "Strain", "HRV", "RHR"],
            "datasets": [
                {
                    "label": "WHOOP",
                    "data": [round(recovery, 1), round(sleep_eff, 1), round(strain_pct, 1), round(hrv_pct, 1), round(rhr_pct, 1)],
                    "backgroundColor": "rgba(32, 201, 151, 0.28)",
                    "borderColor": "rgb(32, 201, 151)",
                    "pointBackgroundColor": "rgb(255,255,255)",
                    "borderWidth": 2,
                }
            ],
        },
        "options": {
            "plugins": {"legend": {"display": False}, "title": {"display": True, "text": "WHOOP Daily Dashboard"}},
            "scale": {"ticks": {"beginAtZero": True, "max": 100}},
        },
    }
    return "https://quickchart.io/chart?width=900&height=520&c=" + quote(json.dumps(cfg, separators=(",", ":")))


def telegram_send(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    http_json(
        "POST",
        url,
        json_body={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
    )


def telegram_send_photo_url(bot_token: str, chat_id: str, photo_url: str, caption: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    http_json(
        "POST",
        url,
        json_body={
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
            "disable_notification": True,
        },
    )


def fetch_latest_or_none(client: WhoopClient, access_token: str, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        payload = client.get_json(access_token, path, params=params)
        return first_record(payload)
    except HttpError as exc:
        status = exc.status
        if status == 404:
            return None
        raise


def run_send_report(dry_run: bool = False, force: bool = False) -> int:
    load_dotenv_file()

    client_id = env("WHOOP_CLIENT_ID", required=True)
    client_secret = env("WHOOP_CLIENT_SECRET", required=True)
    refresh_token = env("WHOOP_REFRESH_TOKEN", required=True)
    token_url = env("WHOOP_TOKEN_URL", "https://api.prod.whoop.com/oauth/oauth2/token")
    api_base = env("WHOOP_API_BASE", "https://api.prod.whoop.com/developer/v2")
    tz_name = env("REPORT_TIMEZONE", "Europe/Moscow")
    lookback_raw = to_int(env("LOOKBACK_DAYS", "0"))
    lookback_days = 0 if lookback_raw is None else max(0, lookback_raw)
    activity_lookback_default = str(lookback_days)
    activity_lookback_raw = to_int(env("ACTIVITY_LOOKBACK_DAYS", activity_lookback_default))
    activity_lookback_days = 0 if activity_lookback_raw is None else max(0, activity_lookback_raw)
    profile = load_user_profile()

    tz = ZoneInfo(tz_name)
    now_local = dt.datetime.now(tz)
    current_day = now_local.date()
    target_day = (now_local - dt.timedelta(days=lookback_days)).date()
    activity_day = (now_local - dt.timedelta(days=activity_lookback_days)).date()
    state = load_state()
    day_key = target_day.isoformat()
    if not dry_run and not force and state.get("daily_sent", {}).get(day_key):
        print(f"Пропуск: дневной отчёт за {day_key} уже отправлялся")
        return 0

    start_local = dt.datetime.combine(activity_day, dt.time.min, tzinfo=tz)
    end_local = dt.datetime.combine(activity_day, dt.time.max, tzinfo=tz)

    client = WhoopClient(client_id, client_secret, refresh_token, token_url, api_base)

    token_data = client.refresh_access_token()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("WHOOP не вернул access_token")

    new_refresh_token = token_data.get("refresh_token")
    if new_refresh_token and new_refresh_token != refresh_token:
        update_env_value("WHOOP_REFRESH_TOKEN", str(new_refresh_token))
        os.environ["WHOOP_REFRESH_TOKEN"] = str(new_refresh_token)
        print("Новый refresh_token получен и сохранён в .env", file=sys.stderr)

    recovery_payload = client.get_json(access_token, "/recovery", {"limit": 7})
    sleep_payload = client.get_json(access_token, "/activity/sleep", {"limit": 7})
    cycle_payload = client.get_json(access_token, "/cycle", {"limit": 7})

    recovery_records = records_list(recovery_payload)
    sleep_records = records_list(sleep_payload)
    cycle_records = records_list(cycle_payload)

    allow_fallback = lookback_days != 0
    recovery = pick_record_for_date(recovery_records, target_day, tz, allow_fallback=allow_fallback)
    sleep = pick_record_for_date(sleep_records, target_day, tz, allow_fallback=allow_fallback)
    cycle = pick_record_for_date(cycle_records, activity_day, tz, allow_fallback=allow_fallback)

    header_note = None
    if lookback_days == 0 and not any([recovery, sleep, cycle]):
        newest_dates = []
        for rec in (recovery_records[:1] + sleep_records[:1] + cycle_records[:1]):
            d = record_local_date(rec, tz)
            if d is not None:
                newest_dates.append(d)
        if newest_dates:
            latest = max(newest_dates).isoformat()
            header_note = f"Данные за сегодня ещё не готовы в WHOOP. Последняя доступная дата: {latest}."
        else:
            header_note = "Данные за сегодня ещё не готовы в WHOOP."

    workouts_payload = client.get_json(
        access_token,
        "/activity/workout",
        params={
            "start": start_local.astimezone(dt.timezone.utc).isoformat(),
            "end": end_local.astimezone(dt.timezone.utc).isoformat(),
            "limit": 25,
        },
    )
    activity_payload = safe_get_json(
        client,
        access_token,
        "/activity",
        params={
            "start": start_local.astimezone(dt.timezone.utc).isoformat(),
            "end": end_local.astimezone(dt.timezone.utc).isoformat(),
            "limit": 25,
        },
    )
    steps_count = extract_steps_count([activity_payload, workouts_payload, cycle])
    steps_note = None
    if steps_count is None:
        estimated_steps = estimate_steps_from_workouts(workouts_payload)
        if estimated_steps is not None:
            steps_count = estimated_steps
            steps_note = "оценка по дистанции тренировки"

    report = build_report_text(
        tz_name,
        target_day,
        activity_day,
        current_day,
        recovery,
        sleep,
        cycle,
        workouts_payload,
        steps_count=steps_count,
        steps_note=steps_note,
        profile=profile,
        lookback_days=lookback_days,
        header_note=header_note,
        recovery_records=recovery_records,
        sleep_records=sleep_records,
        cycle_records=cycle_records,
    )
    rec = extract_recovery_metrics(recovery or {})
    slp = extract_sleep_metrics(sleep or {})
    day_strain = extract_strain(cycle or {})

    if dry_run:
        print(report)
        return 0

    bot_token = env("TELEGRAM_BOT_TOKEN", required=True)
    chat_id = env("TELEGRAM_CHAT_ID", required=True)
    if env("REPORT_SEND_IMAGE", "1") == "1":
        chart_url = build_dashboard_chart_url(rec, slp, day_strain)
        try:
            telegram_send_photo_url(
                bot_token,
                chat_id,
                chart_url,
                f"<b>WHOOP визуальная карточка</b>\n{target_day.isoformat()}",
            )
        except Exception as exc:
            print(f"Предупреждение: не удалось отправить карточку: {exc}", file=sys.stderr)
    telegram_send(bot_token, chat_id, report)
    state.setdefault("daily_sent", {})[day_key] = dt.datetime.now(dt.timezone.utc).isoformat()
    save_state(state)
    print("Отчёт отправлен в Telegram")
    return 0


def run_send_weekly(dry_run: bool = False, force: bool = False) -> int:
    load_dotenv_file()

    client_id = env("WHOOP_CLIENT_ID", required=True)
    client_secret = env("WHOOP_CLIENT_SECRET", required=True)
    refresh_token = env("WHOOP_REFRESH_TOKEN", required=True)
    token_url = env("WHOOP_TOKEN_URL", "https://api.prod.whoop.com/oauth/oauth2/token")
    api_base = env("WHOOP_API_BASE", "https://api.prod.whoop.com/developer/v2")
    tz_name = env("REPORT_TIMEZONE", "Europe/Moscow")

    tz = ZoneInfo(tz_name)
    now_local = dt.datetime.now(tz)
    week_end = (now_local - dt.timedelta(days=1)).date()
    week_start = week_end - dt.timedelta(days=6)
    week_key = f"{week_start.isoformat()}_{week_end.isoformat()}"

    state = load_state()
    if not dry_run and not force and state.get("weekly_sent", {}).get(week_key):
        print(f"Пропуск: недельный отчёт {week_key} уже отправлялся")
        return 0

    client = WhoopClient(client_id, client_secret, refresh_token, token_url, api_base)
    token_data = client.refresh_access_token()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("WHOOP не вернул access_token")
    new_refresh_token = token_data.get("refresh_token")
    if new_refresh_token and new_refresh_token != refresh_token:
        update_env_value("WHOOP_REFRESH_TOKEN", str(new_refresh_token))
        os.environ["WHOOP_REFRESH_TOKEN"] = str(new_refresh_token)
        print("Новый refresh_token получен и сохранён в .env", file=sys.stderr)

    recovery_records_all = records_list(client.get_json(access_token, "/recovery", {"limit": 25}))
    sleep_records_all = records_list(client.get_json(access_token, "/activity/sleep", {"limit": 25}))
    cycle_records_all = records_list(client.get_json(access_token, "/cycle", {"limit": 25}))

    def in_week(rec: Dict[str, Any]) -> bool:
        d = record_local_date(rec, tz)
        return d is not None and week_start <= d <= week_end

    recovery_records = [r for r in recovery_records_all if in_week(r)]
    sleep_records = [r for r in sleep_records_all if in_week(r)]
    cycle_records = [r for r in cycle_records_all if in_week(r)]

    start_local = dt.datetime.combine(week_start, dt.time.min, tzinfo=tz)
    end_local = dt.datetime.combine(week_end, dt.time.max, tzinfo=tz)
    workouts_payload = client.get_json(
        access_token,
        "/activity/workout",
        params={
            "start": start_local.astimezone(dt.timezone.utc).isoformat(),
            "end": end_local.astimezone(dt.timezone.utc).isoformat(),
            "limit": 25,
        },
    )
    workouts_count = extract_workout_count(workouts_payload)
    report = build_weekly_report_text(
        tz_name,
        week_start,
        week_end,
        recovery_records,
        sleep_records,
        cycle_records,
        workouts_count,
    )

    if dry_run:
        print(report)
        return 0

    bot_token = env("TELEGRAM_BOT_TOKEN", required=True)
    chat_id = env("TELEGRAM_CHAT_ID", required=True)
    telegram_send(bot_token, chat_id, report)
    state.setdefault("weekly_sent", {})[week_key] = dt.datetime.now(dt.timezone.utc).isoformat()
    save_state(state)
    print("Недельный отчёт отправлен в Telegram")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="WHOOP -> Telegram утренний отчёт")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("auth-url", help="Сгенерировать URL для OAuth-авторизации")

    p_exchange = sub.add_parser("exchange-code", help="Обменять authorization code на токены")
    p_exchange.add_argument("code", help="Параметр code из redirect URL")

    p_send = sub.add_parser("send-report", help="Забрать метрики и отправить дневной отчёт")
    p_send.add_argument("--dry-run", action="store_true", help="Показать отчёт в stdout без отправки в Telegram")
    p_send.add_argument("--force", action="store_true", help="Игнорировать защиту от дублей и отправить повторно")

    p_week = sub.add_parser("send-weekly", help="Собрать и отправить недельный отчёт")
    p_week.add_argument("--dry-run", action="store_true", help="Показать отчёт в stdout без отправки в Telegram")
    p_week.add_argument("--force", action="store_true", help="Игнорировать защиту от дублей и отправить повторно")

    p_auto = sub.add_parser("send-auto", help="Дневной отчёт + недельный по воскресеньям")
    p_auto.add_argument("--dry-run", action="store_true", help="Показать отчёты в stdout без отправки в Telegram")
    p_auto.add_argument("--force", action="store_true", help="Игнорировать защиту от дублей и отправить повторно")

    args = parser.parse_args(list(argv) if argv is not None else None)
    load_dotenv_file()

    try:
        if args.cmd == "auth-url":
            auth_data = build_auth_url()
            print("state:", auth_data["state"])
            print(auth_data["url"])
            return 0
        if args.cmd == "exchange-code":
            tokens = exchange_code(args.code)
            print("access_token:", tokens.get("access_token", ""))
            print("refresh_token:", tokens.get("refresh_token", ""))
            print("expires_in:", tokens.get("expires_in", ""))
            return 0
        if args.cmd == "send-weekly":
            return run_send_weekly(dry_run=bool(args.dry_run), force=bool(args.force))
        if args.cmd == "send-auto":
            rc = run_send_report(dry_run=bool(args.dry_run), force=bool(args.force))
            if rc != 0:
                return rc
            tz = ZoneInfo(env("REPORT_TIMEZONE", "Europe/Moscow"))
            today = dt.datetime.now(tz).date()
            if today.weekday() == 6:  # воскресенье
                return run_send_weekly(dry_run=bool(args.dry_run), force=bool(args.force))
            return 0

        dry_run = bool(getattr(args, "dry_run", False))
        force = bool(getattr(args, "force", False))
        return run_send_report(dry_run=dry_run, force=force)
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
