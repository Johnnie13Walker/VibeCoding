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

    assert "WHOOP · 26 мая · вт" in text
    assert "ПЛАН:" in text
    assert "Метрики vs baseline 30д:" in text
    assert "<b>" not in text
    assert "Профиль" not in text
    assert "План Б" not in text
    assert "____" not in text


def test_env_bool_accepts_russian_yes(monkeypatch):
    report = _load_report_module()
    monkeypatch.setenv("LARISA_WHOOP_PILOT", "да")

    assert report.env_bool("LARISA_WHOOP_PILOT") is True


def test_new_renderer_failure_falls_back_to_old(monkeypatch, tmp_path, capsys):
    """Если новый renderer падает, dry-run печатает старый формат и возвращает 0."""
    report = _load_report_module()

    class FakeWhoopClient:
        def __init__(self, *args, **kwargs):
            pass

        def refresh_access_token(self):
            return {"access_token": "test-access-token"}

    monkeypatch.setenv("WHOOP_STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("WHOOP_CLIENT_ID", "client")
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", "secret")
    monkeypatch.setenv("WHOOP_REFRESH_TOKEN", "refresh")
    monkeypatch.setenv("WHOOP_REPORT_RETRY_ATTEMPTS", "0")
    monkeypatch.setattr(report, "WhoopClient", FakeWhoopClient)
    monkeypatch.setattr(report, "get_json_logged", lambda *args, **kwargs: [])
    monkeypatch.setattr(report, "build_new_report_text", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("renderer boom")))

    rc = report.run_send_report(dry_run=True, force=True)

    captured = capsys.readouterr()
    assert rc == 0
    assert "<b>WHOOP: отчёт за" in captured.out  # старый формат в fallback
    assert "NEW renderer fail, fallback to OLD" in captured.err
    assert "renderer boom" in captured.err
