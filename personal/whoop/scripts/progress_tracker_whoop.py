#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

TZ_NAME = os.getenv("TZ", "Europe/Moscow")
TZ = ZoneInfo(TZ_NAME)
WHOOP_OPENAPI_URL = "https://api.prod.whoop.com/developer/doc/openapi.json"


class AppError(RuntimeError):
    pass


def now_local() -> dt.datetime:
    return dt.datetime.now(TZ)


def load_env_file(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def env(name: str, default: Optional[str] = None, required: bool = False) -> str:
    v = os.getenv(name, default)
    if required and not v:
        raise AppError(f"Не задана переменная окружения: {name}")
    return v or ""


def to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


@dataclass
class WhoopMetric:
    name: str
    scope: str
    value: float
    timestamp: dt.datetime


@dataclass
class ForecastResult:
    final: float
    linear: float
    profile: float
    reliable: bool
    profile_kind: str


class Store:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tokens (
              provider TEXT PRIMARY KEY,
              access_token TEXT,
              refresh_token TEXT,
              expires_at INTEGER,
              token_type TEXT,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS samples (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              timestamp TEXT NOT NULL,
              day TEXT NOT NULL,
              progress_value REAL NOT NULL,
              metric_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS daily_state (
              day TEXT PRIMARY KEY,
              sent_count INTEGER NOT NULL DEFAULT 0,
              last_forecast REAL,
              paused INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              day TEXT NOT NULL,
              ping_key TEXT NOT NULL,
              sent_at TEXT NOT NULL,
              message TEXT NOT NULL,
              UNIQUE(day, ping_key)
            );
            """
        )
        self.conn.commit()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings(key, value, updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, dt.datetime.now(dt.timezone.utc).isoformat()),
        )
        self.conn.commit()

    def save_tokens(self, provider: str, payload: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO tokens(provider, access_token, refresh_token, expires_at, token_type, updated_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(provider) DO UPDATE SET
              access_token=excluded.access_token,
              refresh_token=excluded.refresh_token,
              expires_at=excluded.expires_at,
              token_type=excluded.token_type,
              updated_at=excluded.updated_at
            """,
            (
                provider,
                payload.get("access_token"),
                payload.get("refresh_token"),
                payload.get("expires_at"),
                payload.get("token_type"),
                dt.datetime.now(dt.timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def load_tokens(self, provider: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM tokens WHERE provider=?", (provider,)).fetchone()
        if not row:
            return None
        return dict(row)

    def insert_sample(self, ts: dt.datetime, day: str, value: float, metric_name: str) -> None:
        self.conn.execute(
            "INSERT INTO samples(timestamp, day, progress_value, metric_name) VALUES(?,?,?,?)",
            (ts.isoformat(), day, value, metric_name),
        )
        self.conn.commit()

    def get_samples_days(self, metric_name: str, days: int) -> List[sqlite3.Row]:
        cutoff = (now_local().date() - dt.timedelta(days=days - 1)).isoformat()
        return list(
            self.conn.execute(
                "SELECT * FROM samples WHERE metric_name=? AND day>=? ORDER BY timestamp ASC",
                (metric_name, cutoff),
            ).fetchall()
        )

    def mark_sent(self, day: str, ping_key: str, message: str, forecast: Optional[float]) -> bool:
        try:
            self.conn.execute(
                "INSERT INTO notifications(day,ping_key,sent_at,message) VALUES(?,?,?,?)",
                (day, ping_key, now_local().isoformat(), message),
            )
            self.conn.execute(
                """
                INSERT INTO daily_state(day,sent_count,last_forecast,paused,updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(day) DO UPDATE SET
                  sent_count=sent_count+1,
                  last_forecast=excluded.last_forecast,
                  updated_at=excluded.updated_at
                """,
                (day, 1, forecast, 0, now_local().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def sent_count(self, day: str) -> int:
        row = self.conn.execute("SELECT sent_count FROM daily_state WHERE day=?", (day,)).fetchone()
        return int(row[0]) if row else 0

    def has_ping(self, day: str, ping_key: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM notifications WHERE day=? AND ping_key=?", (day, ping_key)).fetchone()
        return bool(row)


class WhoopClient:
    def __init__(self, store: Store):
        self.store = store
        self.client_id = env("WHOOP_CLIENT_ID", required=True)
        self.client_secret = env("WHOOP_CLIENT_SECRET", required=True)
        self.redirect_uri = env("WHOOP_REDIRECT_URI", required=True)
        self.token_url = env("WHOOP_TOKEN_URL", "https://api.prod.whoop.com/oauth/oauth2/token")
        self.api_base = env("WHOOP_API_BASE", "https://api.prod.whoop.com/developer/v2").rstrip("/")

    @staticmethod
    def _http_json(method: str, url: str, headers: Optional[Dict[str, str]] = None, form: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        h = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        if headers:
            h.update(headers)
        data = None
        if form is not None:
            h["Content-Type"] = "application/x-www-form-urlencoded"
            data = urlencode(form).encode()
        req = Request(url, data=data, headers=h, method=method.upper())
        try:
            with urlopen(req, timeout=30) as resp:
                payload = resp.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AppError(f"HTTP {exc.code}: {body}")
        except URLError as exc:
            raise AppError(f"Сетевая ошибка: {exc}")

    def auth_url(self) -> str:
        state = os.urandom(16).hex()
        self.store.set_setting("oauth_state", state)
        qs = urlencode(
            {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": self.redirect_uri,
                "scope": "read:cycles offline",
                "state": state,
            }
        )
        return f"https://api.prod.whoop.com/oauth/oauth2/auth?{qs}"

    def exchange_code(self, code: str) -> Dict[str, Any]:
        tok = self._http_json(
            "POST",
            self.token_url,
            headers={"Origin": "https://developer.whoop.com", "Referer": "https://developer.whoop.com/"},
            form={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
            },
        )
        expires_in = int(tok.get("expires_in", 3600))
        tok["expires_at"] = int(dt.datetime.now(dt.timezone.utc).timestamp()) + max(60, expires_in - 60)
        self.store.save_tokens("whoop", tok)
        return tok

    def _refresh(self, refresh_token: str) -> Dict[str, Any]:
        tok = self._http_json(
            "POST",
            self.token_url,
            headers={"Origin": "https://developer.whoop.com", "Referer": "https://developer.whoop.com/"},
            form={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        expires_in = int(tok.get("expires_in", 3600))
        tok["expires_at"] = int(dt.datetime.now(dt.timezone.utc).timestamp()) + max(60, expires_in - 60)
        self.store.save_tokens("whoop", tok)
        return tok

    def access_token(self) -> str:
        row = self.store.load_tokens("whoop")
        env_refresh = env("WHOOP_REFRESH_TOKEN", "")
        now_ts = int(dt.datetime.now(dt.timezone.utc).timestamp())

        if row and row.get("access_token") and int(row.get("expires_at") or 0) > now_ts:
            return str(row["access_token"])

        refresh = str((row or {}).get("refresh_token") or env_refresh)
        if not refresh:
            raise AppError("Нет refresh_token. Выполните auth-url/exchange-code.")
        tok = self._refresh(refresh)
        # sync rotated token to env file if configured
        env_file = env("WHOOP_TOKEN_CACHE_PATH", "")
        if env_file:
            p = Path(env_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(tok, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(tok["access_token"])

    def get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        token = self.access_token()
        url = f"{self.api_base}{path}?{urlencode(params)}"
        return self._http_json("GET", url, headers={"Authorization": f"Bearer {token}"})


class Tracker:
    def __init__(self, store: Store, whoop: WhoopClient):
        self.store = store
        self.whoop = whoop
        self.metric_name = env("PROGRESS_METRIC", "kilojoule")
        self.goal_default = float(env("PROGRESS_GOAL_DEFAULT", "10000"))
        self.max_pings = int(env("PROGRESS_MAX_PINGS_PER_DAY", "6"))
        self.profile_window_days = 21
        self.profile_min_days = 7

    def goal(self) -> float:
        v = self.store.get_setting("goal", None)
        return float(v) if v is not None else self.goal_default

    def set_goal(self, value: float) -> None:
        self.store.set_setting("goal", str(value))

    def pings_enabled(self) -> bool:
        if env("PROGRESS_PINGS_ENABLED", "1") == "0":
            return False
        v = self.store.get_setting("pings_enabled", "1")
        return v != "0"

    def set_pings_enabled(self, enabled: bool) -> None:
        self.store.set_setting("pings_enabled", "1" if enabled else "0")

    def diagnose_steps(self) -> Dict[str, Any]:
        try:
            req = Request(WHOOP_OPENAPI_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urlopen(req, timeout=30) as resp:
                spec = resp.read().decode("utf-8")
        except Exception as exc:
            raise AppError(f"Не удалось загрузить WHOOP OpenAPI: {exc}")

        lowered = spec.lower()
        step_keywords = ["step", "steps", "step_count", "distance_walked"]
        found_steps = any(k in lowered for k in step_keywords)
        return {
            "openapi_url": WHOOP_OPENAPI_URL,
            "steps_available": found_steps,
            "checked_keywords": step_keywords,
            "required_scope_for_selected_metric": "read:cycles",
            "selected_metric": self.metric_name,
        }

    def fetch_today_progress(self) -> WhoopMetric:
        now = now_local()
        day_start = dt.datetime.combine(now.date(), dt.time.min, tzinfo=TZ)
        payload = self.whoop.get(
            "/cycle",
            {
                "start": day_start.astimezone(dt.timezone.utc).isoformat(),
                "end": now.astimezone(dt.timezone.utc).isoformat(),
                "limit": 25,
            },
        )
        records = payload.get("records") or []
        val = None
        ts = now
        for rec in records:
            score = rec.get("score") or {}
            if not isinstance(score, dict):
                continue
            if self.metric_name == "kilojoule":
                val = to_float(score.get("kilojoule"))
            elif self.metric_name == "strain":
                val = to_float(score.get("strain"))
            else:
                val = to_float(score.get("kilojoule"))
            if val is not None:
                t = rec.get("updated_at") or rec.get("created_at")
                if t:
                    ts = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00")).astimezone(TZ)
                break
        if val is None:
            val = 0.0
        return WhoopMetric(name=self.metric_name, scope="read:cycles", value=val, timestamp=ts)

    def _day_progress(self, day: str) -> List[sqlite3.Row]:
        rows = self.store.get_samples_days(self.metric_name, 60)
        return [r for r in rows if r["day"] == day]

    @staticmethod
    def _is_weekend(day_iso: str) -> bool:
        d = dt.date.fromisoformat(day_iso)
        return d.weekday() >= 5

    @staticmethod
    def _smooth_share(share: List[float]) -> List[float]:
        if len(share) != 24:
            return share
        out: List[float] = []
        for h in range(24):
            prev_v = share[h - 1] if h > 0 else share[h]
            next_v = share[h + 1] if h < 23 else share[h]
            out.append(0.25 * prev_v + 0.5 * share[h] + 0.25 * next_v)
        return [max(0.0, min(1.0, v)) for v in out]

    def _build_profiles(self, today: str) -> Dict[str, Any]:
        rows = self.store.get_samples_days(self.metric_name, self.profile_window_days)
        grouped: Dict[str, List[sqlite3.Row]] = {}
        for r in rows:
            if r["day"] == today:
                continue
            grouped.setdefault(r["day"], []).append(r)

        daily_shares: Dict[str, Dict[int, float]] = {}
        for day, items in grouped.items():
            items.sort(key=lambda x: x["timestamp"])
            total = max(float(x["progress_value"]) for x in items)
            if total <= 0:
                continue
            share_map: Dict[int, float] = {}
            last_val = 0.0
            idx = 0
            for h in range(24):
                while idx < len(items):
                    ts_h = dt.datetime.fromisoformat(items[idx]["timestamp"]).astimezone(TZ).hour
                    if ts_h <= h:
                        last_val = float(items[idx]["progress_value"])
                        idx += 1
                    else:
                        break
                share_map[h] = max(0.0, min(1.0, last_val / total))
            daily_shares[day] = share_map

        def aggregate(days: List[str]) -> Dict[str, Any]:
            if not days:
                return {"days": 0, "share": [0.0] * 24}
            hourly: List[float] = []
            for h in range(24):
                vals = [daily_shares[d][h] for d in days]
                hourly.append(float(statistics.median(vals)) if vals else 0.0)
            return {"days": len(days), "share": self._smooth_share(hourly)}

        all_days = sorted(daily_shares.keys())
        weekday_days = [d for d in all_days if not self._is_weekend(d)]
        weekend_days = [d for d in all_days if self._is_weekend(d)]
        return {
            "as_of_day": today,
            "generated_at": now_local().isoformat(),
            "window_days": self.profile_window_days,
            "min_days": self.profile_min_days,
            "profiles": {
                "all": aggregate(all_days),
                "weekday": aggregate(weekday_days),
                "weekend": aggregate(weekend_days),
            },
        }

    def ensure_profiles(self, now: dt.datetime) -> Dict[str, Any]:
        today = now.date().isoformat()
        raw = self.store.get_setting("activity_profiles", "")
        cached: Optional[Dict[str, Any]] = None
        if raw:
            try:
                cached = json.loads(raw)
            except Exception:
                cached = None
        # Пересчет ежедневно: либо поздно вечером, либо при первом запуске нового дня.
        must_recalc = True
        if cached and cached.get("as_of_day") == today:
            if now.hour < 23 or (now.hour == 23 and now.minute < 50):
                must_recalc = False
        if must_recalc:
            cached = self._build_profiles(today)
            self.store.set_setting("activity_profiles", json.dumps(cached, ensure_ascii=False))
        return cached or self._build_profiles(today)

    def _profile_choice(self, progress: float, at_time: dt.datetime) -> Tuple[str, float, int]:
        profiles = self.ensure_profiles(at_time).get("profiles", {})
        goal = max(self.goal(), 1.0)
        hour = at_time.hour

        all_prof = profiles.get("all", {"days": 0, "share": [0.0] * 24})
        wd_prof = profiles.get("weekday", {"days": 0, "share": [0.0] * 24})
        we_prof = profiles.get("weekend", {"days": 0, "share": [0.0] * 24})

        is_we_today = at_time.weekday() >= 5
        choice = "weekend" if is_we_today else "weekday"
        if choice == "weekend" and int(we_prof.get("days", 0)) < 4:
            choice = "all"
        if choice == "weekday" and int(wd_prof.get("days", 0)) < 5:
            choice = "all"

        # auto-weekend для буднего дня, если текущий ритм ближе к weekend-профилю.
        if not is_we_today and choice != "all" and int(we_prof.get("days", 0)) >= 4:
            current_share = max(0.0, min(1.0, progress / goal))
            wd_share = float((wd_prof.get("share") or [0.0] * 24)[hour])
            we_share = float((we_prof.get("share") or [0.0] * 24)[hour])
            wd_dev = abs(current_share - wd_share)
            we_dev = abs(current_share - we_share)
            if wd_dev > 0 and we_dev <= wd_dev * 0.7:
                choice = "auto-weekend"

        if choice == "weekday":
            prof = wd_prof
        elif choice in ("weekend", "auto-weekend"):
            prof = we_prof
        else:
            prof = all_prof

        share = float((prof.get("share") or [0.0] * 24)[hour])
        days = int(prof.get("days", 0))
        self.store.set_setting("last_profile_choice", choice)
        return choice, share, days

    def forecast(self, progress: float, at_time: dt.datetime) -> ForecastResult:
        start = dt.datetime.combine(at_time.date(), dt.time(6, 0), tzinfo=TZ)
        end = dt.datetime.combine(at_time.date(), dt.time(23, 59), tzinfo=TZ)
        elapsed_h = max((at_time - start).total_seconds() / 3600.0, 0.05)
        total_h = max((end - start).total_seconds() / 3600.0, 0.1)
        forecast_linear = (progress / elapsed_h) * total_h

        profile_kind, share, n = self._profile_choice(progress, at_time)
        reliable = share > 0.03 and n >= self.profile_min_days
        if reliable:
            forecast_profile = progress / max(share, 0.01)
            final_forecast = 0.7 * forecast_profile + 0.3 * forecast_linear
            return ForecastResult(final_forecast, forecast_linear, forecast_profile, True, profile_kind)
        return ForecastResult(forecast_linear, forecast_linear, forecast_linear, False, profile_kind)

    def compose_message(self, progress: float, when: dt.datetime, label: str) -> Tuple[str, float]:
        goal = self.goal()
        f = self.forecast(progress, when)
        pct = (progress / goal * 100.0) if goal > 0 else 0.0
        left = max(0.0, goal - progress)
        f_pct = (f.final / goal * 100.0) if goal > 0 else 0.0
        metric_title = {
            "kilojoule": "Энергозатраты (кДж)",
            "strain": "Дневная нагрузка (strain)",
            "steps_today": "Шаги за день",
        }.get(self.metric_name, self.metric_name)
        if f.profile_kind in ("weekend", "auto-weekend"):
            tone = "Выходной ритм: идем мягко, но уверенно."
        else:
            tone = "Рабочий ритм: держим план и темп."
        msg = (
            f"<b>{label}</b>\n"
            f"Метрика: <b>{metric_title}</b>\n"
            f"Прогресс: <b>{progress:.1f}</b> / {goal:.1f} ({pct:.0f}%)\n"
            f"Прогноз к 23:59: <b>{f.final:.1f}</b> ({f_pct:.0f}%)\n"
            f"Осталось до цели: <b>{left:.1f}</b>\n"
            f"Профиль дня: <b>{f.profile_kind}</b>\n"
            f"Модель: {'профиль+линейная' if f.reliable else 'линейная'}\n"
            f"{tone}"
        )
        return msg, f.final


def send_telegram(text: str) -> None:
    token = env("TELEGRAM_BOT_TOKEN", "")
    chat_id = env("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы: сообщение только в stdout")
        print(text)
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = Request(
        url,
        data=urlencode(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }
        ).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        _ = resp.read()


def ping_decision(now: dt.datetime, tracker: Tracker, store: Store, progress: float) -> List[str]:
    day = now.date().isoformat()
    keys: List[str] = []
    if now.hour == 10 and now.minute < 10:
        keys.append("mandatory_1000")
    if now.hour == 15 and now.minute < 10:
        keys.append("mandatory_1500")
    if now.hour == 20 and now.minute < 10:
        keys.append("mandatory_2000")

    goal = tracker.goal()
    pct = (progress / goal * 100.0) if goal > 0 else 0.0
    forecast = tracker.forecast(progress, now).final

    if now.hour == 12 and pct < 20:
        keys.append("smart_1200_low20")
    if now.hour == 17 and forecast < goal:
        keys.append("smart_1700_forecast_low")
    if (now.hour > 21 or (now.hour == 21 and now.minute >= 30)) and (goal - progress) <= goal * 0.15:
        keys.append("smart_2130_close")

    out = []
    for k in keys:
        if not store.has_ping(day, k):
            out.append(k)
    return out


def cmd_progress_status(tracker: Tracker, store: Store) -> int:
    m = tracker.fetch_today_progress()
    d = m.timestamp.astimezone(TZ).date().isoformat()
    store.insert_sample(m.timestamp, d, m.value, m.name)
    tracker.ensure_profiles(now_local())
    msg, _ = tracker.compose_message(m.value, now_local(), "Статус сейчас")
    print(msg)
    return 0


def cmd_progress_goal(tracker: Tracker, value: float) -> int:
    tracker.set_goal(value)
    print(f"Новая цель: {value}")
    return 0


def cmd_progress_pause(tracker: Tracker) -> int:
    tracker.set_pings_enabled(False)
    print("Пинги выключены")
    return 0


def cmd_progress_resume(tracker: Tracker) -> int:
    tracker.set_pings_enabled(True)
    print("Пинги включены")
    return 0


def cmd_progress_insights(tracker: Tracker, store: Store) -> int:
    rows = store.get_samples_days(tracker.metric_name, 14)
    if not rows:
        print("Нет данных для аналитики")
        return 0
    by_day: Dict[str, float] = {}
    for r in rows:
        day = r["day"]
        by_day[day] = max(by_day.get(day, 0.0), float(r["progress_value"]))

    last7 = sorted(by_day.keys())[-7:]
    avg7 = statistics.mean(by_day[d] for d in last7) if last7 else 0.0
    goal = tracker.goal()
    close14 = sum(1 for d, v in by_day.items() if v >= goal)
    weekday_days = [d for d in by_day if dt.date.fromisoformat(d).weekday() < 5]
    weekend_days = [d for d in by_day if dt.date.fromisoformat(d).weekday() >= 5]

    def avg_for(days: List[str]) -> float:
        return statistics.mean(by_day[d] for d in days) if days else 0.0

    def close_pct(days: List[str]) -> float:
        if not days:
            return 0.0
        c = sum(1 for d in days if by_day[d] >= goal)
        return c / len(days) * 100.0

    profiles = tracker.ensure_profiles(now_local()).get("profiles", {})
    now = now_local()
    profile_now, _, _ = tracker._profile_choice(progress=by_day.get(now.date().isoformat(), 0.0), at_time=now)

    def peak_windows(share: List[float]) -> List[str]:
        if len(share) != 24:
            return []
        deltas: List[Tuple[int, float]] = []
        prev = 0.0
        for h, cur in enumerate(share):
            deltas.append((h, max(0.0, cur - prev)))
            prev = cur
        top = sorted(deltas, key=lambda x: x[1], reverse=True)[:3]
        return [f"{h:02d}:00-{(h + 1) % 24:02d}:00" for h, _ in top]

    wd_days = int((profiles.get("weekday") or {}).get("days", 0))
    we_days = int((profiles.get("weekend") or {}).get("days", 0))
    wd_peaks = peak_windows((profiles.get("weekday") or {}).get("share") or []) if wd_days > 0 else []
    we_peaks = peak_windows((profiles.get("weekend") or {}).get("share") or []) if we_days > 0 else []

    print(f"Средний итог за 7 дней: {avg7:.1f}")
    print(f"Закрытие цели за 14 дней: {close14}/{len(by_day)} ({(close14/max(1,len(by_day))*100):.0f}%)")
    print(f"Средний итог по будням: {avg_for(weekday_days):.1f}")
    print(f"Средний итог по выходным: {avg_for(weekend_days):.1f}")
    print(f"% закрытия цели по будням: {close_pct(weekday_days):.0f}%")
    print(f"% закрытия цели по выходным: {close_pct(weekend_days):.0f}%")
    print(f"Пиковые окна (будни): {', '.join(wd_peaks) if wd_peaks else 'нет данных'}")
    print(f"Пиковые окна (выходные): {', '.join(we_peaks) if we_peaks else 'нет данных'}")
    print(f"Текущий профиль: {profile_now}")
    return 0


def cmd_scheduler_run(tracker: Tracker, store: Store) -> int:
    if not tracker.pings_enabled():
        print("Пинги отключены")
        return 0
    now = now_local()
    day = now.date().isoformat()
    if store.sent_count(day) >= tracker.max_pings:
        print("Лимит сообщений на день достигнут")
        return 0

    metric = tracker.fetch_today_progress()
    store.insert_sample(metric.timestamp, day, metric.value, metric.name)
    tracker.ensure_profiles(now)

    keys = ping_decision(now, tracker, store, metric.value)
    if not keys:
        print("Сейчас нет триггеров для пинга")
        return 0

    sent = 0
    for key in keys:
        if store.sent_count(day) >= tracker.max_pings:
            break
        title_map = {
            "mandatory_1000": "10:00 — утренний прогресс",
            "mandatory_1500": "15:00 — дневной прогресс",
            "mandatory_2000": "20:00 — вечерний прогресс",
            "smart_1200_low20": "Доп.пинг: к 12:00 прогресс ниже 20%",
            "smart_1700_forecast_low": "Доп.пинг: к 17:00 прогноз ниже цели",
            "smart_2130_close": "Доп.пинг: до цели осталось <= 15%",
        }
        msg, fc = tracker.compose_message(metric.value, now, title_map.get(key, key))
        profile_kind = tracker.forecast(metric.value, now).profile_kind
        print(f"profile_selected={profile_kind} ping_key={key}")
        if key == "smart_1700_forecast_low":
            if profile_kind in ("weekend", "auto-weekend"):
                msg += "\nПлан: мягкий формат — 2 короткие активности по 20–30 минут до вечера."
            else:
                msg += "\nПлан: 2 короткие сессии активности по 20–30 минут до вечера."
        if key == "smart_2130_close":
            if profile_kind in ("weekend", "auto-weekend"):
                msg += "\nВы рядом с целью. Спокойный финишный рывок — и закрыто."
            else:
                msg += "\nВы рядом с целью. Короткая прогулка сейчас — и цель закрыта."
        send_telegram(msg)
        if store.mark_sent(day, key, msg, fc):
            sent += 1
    print(f"Отправлено сообщений: {sent}")
    return 0


def cmd_selftest(tracker: Tracker, store: Store) -> int:
    # 1) OAuth config sanity
    if not env("WHOOP_CLIENT_ID", "") or not env("WHOOP_CLIENT_SECRET", ""):
        raise AppError("WHOOP_CLIENT_ID/WHOOP_CLIENT_SECRET не заданы")
    has_tokens = bool(store.load_tokens("whoop") or env("WHOOP_REFRESH_TOKEN", ""))
    if not has_tokens:
        raise AppError("Нет токенов. Выполните auth-url/exchange-code")

    # 2) one WHOOP request
    m = tracker.fetch_today_progress()
    day = m.timestamp.astimezone(TZ).date().isoformat()
    store.insert_sample(m.timestamp, day, m.value, m.name)
    tracker.ensure_profiles(now_local())
    print(f"WHOOP sample ok: metric={m.name} value={m.value:.2f} ts={m.timestamp.isoformat()}")

    # 3) simulate forecasts and messages
    base = now_local().replace(minute=0, second=0, microsecond=0)
    checkpoints = [base.replace(hour=10), base.replace(hour=15), base.replace(hour=20)]
    for cp in checkpoints:
        txt, _ = tracker.compose_message(m.value, cp, f"Selftest {cp.strftime('%H:%M')}")
        print("-----")
        print(txt)

    # 4) synthetic history for weekend/weekday/auto-weekend profile checks
    sdb = Store(":memory:")
    stracker = Tracker(sdb, tracker.whoop)
    stracker.metric_name = "selftest_metric"
    stracker.set_goal(100.0)
    today = now_local().date()
    for i in range(1, 22):
        d = today - dt.timedelta(days=i)
        is_we = d.weekday() >= 5
        total = 85.0 if is_we else 100.0
        # Выходные: позже старт и более плавный набор. Будни: ранний плотный темп.
        share_map = {10: 0.08, 15: 0.22, 20: 0.55, 23: 1.0} if is_we else {10: 0.18, 15: 0.48, 20: 0.82, 23: 1.0}
        for hour, share in share_map.items():
            ts = dt.datetime.combine(d, dt.time(hour, 0), tzinfo=TZ)
            sdb.insert_sample(ts, d.isoformat(), total * share, stracker.metric_name)
    stracker.ensure_profiles(now_local())

    sat = today
    while sat.weekday() != 5:
        sat += dt.timedelta(days=1)
    sat_t = dt.datetime.combine(sat, dt.time(15, 0), tzinfo=TZ)
    sat_progress = 28.0
    sat_f = stracker.forecast(sat_progress, sat_t)
    sat_msg, _ = stracker.compose_message(sat_progress, sat_t, "Selftest weekend")
    print("-----")
    print(f"weekend case -> profile={sat_f.profile_kind}, forecast={sat_f.final:.1f}")
    print(sat_msg)

    wd = today
    while wd.weekday() >= 5:
        wd += dt.timedelta(days=1)
    wd_t = dt.datetime.combine(wd, dt.time(15, 0), tzinfo=TZ)
    wd_progress = 50.0
    wd_f = stracker.forecast(wd_progress, wd_t)
    wd_msg, _ = stracker.compose_message(wd_progress, wd_t, "Selftest weekday")
    print("-----")
    print(f"weekday case -> profile={wd_f.profile_kind}, forecast={wd_f.final:.1f}")
    print(wd_msg)

    aw_t = dt.datetime.combine(wd, dt.time(15, 0), tzinfo=TZ)
    aw_progress = 25.0
    aw_f = stracker.forecast(aw_progress, aw_t)
    aw_msg, _ = stracker.compose_message(aw_progress, aw_t, "Selftest auto-weekend")
    print("-----")
    print(f"auto-weekend case -> profile={aw_f.profile_kind}, forecast={aw_f.final:.1f}")
    print(aw_msg)

    # 5) steps diagnostic
    diag = tracker.diagnose_steps()
    print("-----")
    print("steps_available:", diag["steps_available"])
    print("selected_metric:", diag["selected_metric"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="10 000/day tracker on WHOOP API")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("auth-url")
    x = sub.add_parser("exchange-code")
    x.add_argument("code")
    sub.add_parser("diagnose-steps")

    sub.add_parser("progress_status")
    g = sub.add_parser("progress_goal")
    g.add_argument("value", type=float)
    sub.add_parser("progress_pause")
    sub.add_parser("progress_resume")
    sub.add_parser("progress_insights")

    sub.add_parser("run-scheduler")
    sub.add_parser("selftest")
    return p


def main() -> int:
    args = build_parser().parse_args()
    load_env_file()
    db_path = env("PROGRESS_DB_PATH", "/Users/pro2kuror/.config/vibecoding/whoop/progress_tracker.sqlite3")
    store = Store(db_path)
    whoop = WhoopClient(store)
    tracker = Tracker(store, whoop)

    try:
        if args.cmd == "auth-url":
            print(whoop.auth_url())
            return 0
        if args.cmd == "exchange-code":
            tok = whoop.exchange_code(args.code)
            print("refresh_token:", tok.get("refresh_token", ""))
            print("expires_in:", tok.get("expires_in", ""))
            return 0
        if args.cmd == "diagnose-steps":
            print(json.dumps(tracker.diagnose_steps(), ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "progress_status":
            return cmd_progress_status(tracker, store)
        if args.cmd == "progress_goal":
            return cmd_progress_goal(tracker, args.value)
        if args.cmd == "progress_pause":
            return cmd_progress_pause(tracker)
        if args.cmd == "progress_resume":
            return cmd_progress_resume(tracker)
        if args.cmd == "progress_insights":
            return cmd_progress_insights(tracker, store)
        if args.cmd == "run-scheduler":
            return cmd_scheduler_run(tracker, store)
        if args.cmd == "selftest":
            return cmd_selftest(tracker, store)
        build_parser().print_help()
        return 0
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
