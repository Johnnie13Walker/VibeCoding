import argparse

from crm_company_enrich import cli
from crm_company_enrich.stages import telemarketing_digest as stage
from crm_company_enrich.stages.telemarketing_stuck_alerts import StuckDeal
from crm_company_enrich.telegram_client import TelegramClient


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send_message(self, text):
        self.sent.append(text)
        return {"ok": True}


class FakeBitrix:
    def __init__(self, deals):
        self.deals = deals

    def list_deals_by_stages(self, *, category_id, stage_ids, closed, select):
        return [
            deal
            for deal in self.deals
            if str(deal.get("STAGE_ID")) in set(stage_ids)
            and str(deal.get("CLOSED", closed)) == closed
        ]


def test_dry_run_returns_preview_no_send():
    tg = FakeTelegram()

    summary = stage.run(object(), dry_run=True, since="2026-05-17", telegram=tg)

    assert summary["dry_run"] is True
    assert "Телемаркетинг" in summary["preview"]
    assert summary["telegram"] == {"skipped": True, "reason": "dry_run"}
    assert summary["telegram_skipped"] is True
    assert tg.sent == []


def test_send_skipped_when_no_token(monkeypatch):
    monkeypatch.delenv("LARISA_BOT_TOKEN", raising=False)
    monkeypatch.delenv("LARISA_CHAT_ID_LARISA", raising=False)

    result = TelegramClient().send_message("test")

    assert result == {"skipped": True, "reason": "no_config"}


def test_cli_warns_when_telegram_skipped(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_make_clients", lambda: (object(), None))
    monkeypatch.setattr(
        stage,
        "run",
        lambda bx, dry_run, since: {
            "dry_run": False,
            "telegram": {"skipped": True, "reason": "no_config"},
            "telegram_skipped": True,
        },
    )

    code = cli.cmd_telemarketing_digest(argparse.Namespace(live=True, since="2026-05-17"))

    captured = capsys.readouterr()
    assert code == 0
    assert "WARN: telegram message skipped: no_config" in captured.err


def test_format_html_includes_section_titles():
    text = stage._format_html(
        [stage.DigestSection("Авто-возврат", ["строка"])],
        "2026-05-17",
    )

    assert "<b>Авто-возврат</b>" in text
    assert "строка" in text


def test_clickable_bitrix_links_format():
    link = stage._deal_link("20872")

    assert link == (
        '<a href="https://belberrycrm.bitrix24.ru/crm/deal/details/20872/">'
        "#20872</a>"
    )


def test_auto_revive_section_parses_csv_groups_by_assignee(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    (tmp_path / "auto_revive_lose.csv").write_text(
        "\n".join(
            [
                "timestamp,deal_id,company_id,old_assignee,new_assignee,due_date,revive_count,status,error",
                "2026-05-17T09:00:00,101,1,999,2772,2026-05-16,1,REVIVED,",
                "2026-05-17T09:01:00,102,1,999,2772,2026-05-16,1,REVIVED,",
                "2026-05-17T09:02:00,103,1,999,2832,2026-05-16,1,FAILED,error",
                "2026-05-16T09:00:00,104,1,999,2832,2026-05-15,1,REVIVED,",
            ]
        ),
        encoding="utf-8",
    )

    section = stage._section_auto_revive(object(), "2026-05-17")

    assert section.lines == [
        '- Дарья (2772): 2 сделок → <a href="https://belberrycrm.bitrix24.ru/crm/deal/details/101/">#101</a>, <a href="https://belberrycrm.bitrix24.ru/crm/deal/details/102/">#102</a>'
    ]


def test_auto_reject_section_breakdown_by_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    (tmp_path / "auto_reject_telemarketing.csv").write_text(
        "\n".join(
            [
                "timestamp,deal_id,company_id,reason_id,reason_desc,assigned_by",
                "2026-05-17T09:00:00,201,1,8538,closed,2772",
                "2026-05-17T09:01:00,202,2,8542,low revenue,2832",
                "2026-05-17T09:02:00,203,3,8542,low revenue,2832",
                "2026-05-16T09:02:00,204,3,8542,low revenue,2832",
            ]
        ),
        encoding="utf-8",
    )

    section = stage._section_auto_reject(object(), "2026-05-17")

    assert section.lines[0].startswith("- 8538 «Бизнес закрылся»: 1 сделок")
    assert section.lines[1].startswith("- 8542 «Выручка &lt;30M»: 2 сделок")


def test_reactivation_section_breakdown_by_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    (tmp_path / "reactivation_apology.csv").write_text(
        "\n".join(
            [
                "timestamp,deal_id,company_id,reason_id,cooldown_months,reactivation_count_after,new_assignee,status",
                "2026-05-17T09:00:00,301,1,8540,12,1,2772,REACTIVATED",
                "2026-05-17T09:01:00,302,2,8546,6,1,2832,REACTIVATED",
                "2026-05-17T09:02:00,303,3,8546,6,1,2832,FAILED",
            ]
        ),
        encoding="utf-8",
    )

    section = stage._section_reactivations(object(), "2026-05-17")

    assert section.lines[0].startswith("- reason 8540: 1 сделок")
    assert section.lines[1].startswith("- reason 8546: 1 сделок")


def test_empty_csv_returns_empty_section(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)
    (tmp_path / "auto_reject_telemarketing.csv").write_text(
        "timestamp,deal_id,company_id,reason_id,reason_desc,assigned_by\n",
        encoding="utf-8",
    )

    section = stage._section_auto_reject(object(), "2026-05-17")

    assert section.lines == []


def test_missing_csv_file_returns_empty_section_not_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "LOG_DIR", tmp_path)

    assert stage._section_auto_revive(object(), "2026-05-17").lines == []
    assert stage._section_auto_reject(object(), "2026-05-17").lines == []


def test_manager_conversions_aggregates_7_days():
    bx = FakeBitrix(
        [
            {"ID": "1", "STAGE_ID": "C50:APOLOGY", "ASSIGNED_BY_ID": "2772", "DATE_MODIFY": "2026-05-17T10:00:00", "CLOSED": "Y"},
            {"ID": "2", "STAGE_ID": "C50:WON", "ASSIGNED_BY_ID": "2772", "DATE_MODIFY": "2026-05-12T10:00:00", "CLOSED": "Y"},
            {"ID": "3", "STAGE_ID": "C50:WON", "ASSIGNED_BY_ID": "2832", "DATE_MODIFY": "2026-05-17T10:00:00", "CLOSED": "Y"},
            {"ID": "4", "STAGE_ID": "C50:APOLOGY", "ASSIGNED_BY_ID": "2772", "DATE_MODIFY": "2026-05-01T10:00:00", "CLOSED": "Y"},
        ]
    )

    section = stage._section_manager_conversions(bx, "2026-05-17")

    assert "- Дарья: APOLOGY 1 / WON 1" in section.lines
    assert "- Аркадий: APOLOGY 0 / WON 1" in section.lines


def test_stuck_alerts_aggregates_open_deals():
    bx = FakeBitrix([
        {"ID": "1", "TITLE": "prep", "STAGE_ID": "C50:PREPARATION", "CLOSED": "N", "DATE_MODIFY": "2999-04-01"},
        {"ID": "2", "TITLE": "meet", "STAGE_ID": "C50:UC_WZ4KQE", "CLOSED": "N", "CLOSEDATE": "2999-04-01"},
    ])

    section = stage._section_stuck_alerts(bx)

    assert section.lines == []


def test_section_returns_empty_when_no_data():
    bx = FakeBitrix([])

    assert stage._section_manager_conversions(bx, "2026-05-17").lines == []
    assert stage._section_stuck_alerts(bx).lines == []


def test_stuck_alerts_section_includes_preparation_links(monkeypatch):
    monkeypatch.setattr(
        "crm_company_enrich.stages.telemarketing_stuck_alerts.find_stuck_preparation",
        lambda bx: [StuckDeal("11", "Сделка", "2772", "C50:PREPARATION", 22, "no_communication_21d")],
    )
    monkeypatch.setattr(
        "crm_company_enrich.stages.telemarketing_stuck_alerts.find_stuck_wz4kqe",
        lambda bx: [],
    )

    section = stage._section_stuck_alerts(object())

    assert "PREPARATION" in section.lines[0]
    assert 'href="https://belberrycrm.bitrix24.ru/crm/deal/details/11/"' in section.lines[1]


def test_stuck_alerts_section_includes_wz4kqe_links(monkeypatch):
    monkeypatch.setattr(
        "crm_company_enrich.stages.telemarketing_stuck_alerts.find_stuck_preparation",
        lambda bx: [],
    )
    monkeypatch.setattr(
        "crm_company_enrich.stages.telemarketing_stuck_alerts.find_stuck_wz4kqe",
        lambda bx: [StuckDeal("12", "Встреча", "2832", "C50:UC_WZ4KQE", 15, "meeting_overdue_14d")],
    )

    section = stage._section_stuck_alerts(object())

    assert "WZ4KQE" in section.lines[0]
    assert 'href="https://belberrycrm.bitrix24.ru/crm/deal/details/12/"' in section.lines[1]


def test_stuck_alerts_section_caps_at_5_per_category(monkeypatch):
    deals = [
        StuckDeal(str(i), f"Сделка {i}", "2772", "C50:PREPARATION", 30, "no_communication_21d")
        for i in range(1, 7)
    ]
    monkeypatch.setattr(
        "crm_company_enrich.stages.telemarketing_stuck_alerts.find_stuck_preparation",
        lambda bx: deals,
    )
    monkeypatch.setattr(
        "crm_company_enrich.stages.telemarketing_stuck_alerts.find_stuck_wz4kqe",
        lambda bx: [],
    )

    section = stage._section_stuck_alerts(object())

    assert sum("crm/deal/details" in line for line in section.lines) == 5
    assert section.lines[-1] == "  + ещё 1"
