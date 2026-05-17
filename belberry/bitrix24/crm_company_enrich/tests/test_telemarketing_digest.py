from crm_company_enrich.stages import telemarketing_digest as stage
from crm_company_enrich.telegram_client import TelegramClient


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send_message(self, text):
        self.sent.append(text)
        return {"ok": True}


def test_dry_run_returns_preview_no_send():
    tg = FakeTelegram()

    summary = stage.run(object(), dry_run=True, since="2026-05-17", telegram=tg)

    assert summary["dry_run"] is True
    assert "Телемаркетинг" in summary["preview"]
    assert tg.sent == []


def test_send_skipped_when_no_token(monkeypatch):
    monkeypatch.delenv("LARISA_BOT_TOKEN", raising=False)
    monkeypatch.delenv("LARISA_CHAT_ID_LARISA", raising=False)

    result = TelegramClient().send_message("test")

    assert result == {"skipped": True, "reason": "no_config"}


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
