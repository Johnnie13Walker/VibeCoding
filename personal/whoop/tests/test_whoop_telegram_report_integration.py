import datetime as dt
import importlib.util
from pathlib import Path


def _load_report_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "whoop_telegram_report.py"
    spec = importlib.util.spec_from_file_location("whoop_telegram_report", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_new_report_text_uses_template_renderer(monkeypatch, tmp_path):
    monkeypatch.setenv("WHOOP_STATE_FILE", str(tmp_path / "state.json"))
    report = _load_report_module()
    recovery = {"score": {"recovery_score": 78, "hrv_rmssd_milli": 60, "resting_heart_rate": 62, "spo2_percentage": 98}}
    sleep = {"score": {"sleep_performance_percentage": 92, "sleep_efficiency_percentage": 91}, "score_state": "SCORED", "total_in_bed_time_milli": 8 * 60 * 60 * 1000}
    cycle = {"score": {"strain": 8.2}}

    text = report.build_new_report_text(
        tz_name="Europe/Moscow",
        report_date=dt.date(2026, 5, 26),
        recovery=recovery,
        sleep=sleep,
        cycle=cycle,
        recovery_records=[],
        sleep_records=[],
        cycle_records=[],
    )

    assert "<b>WHOOP · 26 мая · вт</b>" in text
    assert "ПЛАН НА СЕГОДНЯ" in text
    assert "Профиль" not in text
    assert "План Б" not in text

