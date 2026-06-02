import json
from datetime import date
from pathlib import Path

import pytest

from src import bx_client
from src.collect import collect_day, collect_users_and_photos
from src.timeutil import next_working_day

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "2026-05-29"


class FakeBx:
    def __init__(self):
        self.fetches = []
        self.calls = []

    def fetch_all(self, method, params=None, idfield="ID", cap=5000):
        self.fetches.append((method, params or {}, idfield))
        if method == "crm.deal.list" and "DATE_CREATE" in str(params):
            return [{"ID": "10", "TITLE": "new deal", "ASSIGNED_BY_ID": "1"}]
        if method == "crm.deal.list":
            return [
                {
                    "ID": "20",
                    "TITLE": "open deal",
                    "CATEGORY_ID": "10",
                    "STAGE_ID": "C10:EXECUTING",
                    "ASSIGNED_BY_ID": "1",
                    "MOVED_TIME": "2026-05-01T10:00:00+03:00",
                    "LAST_ACTIVITY_TIME": "2026-05-28T10:00:00+03:00",
                }
            ]
        if method == "crm.stagehistory.list":
            return [{"ID": 1, "OWNER_ID": 20, "STAGE_ID": "C10:LOSE"}]
        if method == "crm.item.list":
            entity_type = params["entityTypeId"]
            if entity_type == 1048 and "ufCrm16_1751009238" in str(params):
                lower = params["filter"].get(">=ufCrm16_1751009238", "")
                if lower.startswith(next_working_day(date(2026, 5, 29)).isoformat()):
                    return [
                        {
                            "id": 104,
                            "title": "future meeting",
                            "assignedById": 1,
                            "parentId2": 20,
                            "ufCrm16_1751009238": "2026-06-01T10:00:00+03:00",
                        }
                    ]
                if lower.startswith("2026-05-29"):
                    return [
                        {
                            "id": 103,
                            "title": "day meeting",
                            "assignedById": 1,
                            "parentId2": 20,
                            "ufCrm16_1751009238": "2026-05-29T10:00:00+03:00",
                        }
                    ]
            if entity_type == 1048:
                return []
            if entity_type == 1056:
                return [{"id": 1056, "title": "brief", "assignedById": 1, "parentId2": 20}]
            if entity_type == 1106:
                return [{"id": 1106, "title": "kp", "assignedById": 1, "parentId2": 20}]
        if method == "crm.activity.list":
            return [{"ID": "500", "OWNER_ID": "20", "RESPONSIBLE_ID": "1"}]
        return []

    def call(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "voximplant.statistic.get":
            last = int((params or {}).get("FILTER", {}).get(">ID", 0))
            if last == 0:
                return {"result": [{"ID": "1", "PORTAL_USER_ID": "1", "CALL_DURATION": "130"}]}
            return {"result": []}
        if method == "user.get":
            return {"result": [{"ID": "1", "LAST_NAME": "Иванов", "NAME": "Иван"}]}
        if method == "crm.timeline.comment.list":
            return {"result": []}
        return {"result": []}


def test_seed_fixture_has_data_contract_keys():
    raw = json.loads((FIXTURE_DIR / "raw.json").read_text())

    for key in ["deals_open", "meet_day", "stagehistory", "briefs", "kp", "activities"]:
        assert key in raw
        assert isinstance(raw[key], list)


def test_collect_day_uses_fake_client_without_network():
    raw = collect_day(date(2026, 5, 29), bx=FakeBx())

    assert raw["deals_created"]
    assert raw["calls"]
    assert "photos" in raw
    assert raw["users"] == {"1": "Иванов Иван"}


def test_meet_today_uses_next_working_day_not_wall_clock():
    fake = FakeBx()

    raw = collect_day(date(2026, 5, 29), bx=fake)

    assert raw["meet_today"][0]["ufCrm16_1751009238"].startswith("2026-06-01")


def test_fetch_all_cursor_stops_on_empty_page(monkeypatch):
    pages = [
        {"result": [{"ID": 1}, {"ID": 2}]},
        {"result": []},
    ]
    calls = []

    def fake_call(method, params=None):
        calls.append(params)
        return pages.pop(0)

    monkeypatch.setattr(bx_client, "call", fake_call)

    rows = bx_client.fetch_all("crm.deal.list")

    assert rows == [{"ID": 1}, {"ID": 2}]
    assert len(calls) == 2
    assert calls[0]["filter"][">ID"] == 0
    assert calls[1]["filter"][">ID"] == 2
    assert calls[0]["start"] == -1


def test_call_uses_bitrix_timeout_and_retries_env(monkeypatch, tmp_path):
    state = tmp_path / "install.latest.json"
    state.write_text(
        '{"payload":{"auth[client_endpoint]":"https://example.test/rest","auth[access_token]":"token"}}'
    )
    attempts = []

    def fake_post(url, data=None, timeout=None):
        attempts.append(timeout)
        raise bx_client.requests.exceptions.Timeout("slow handshake")

    class FakeSession:
        post = staticmethod(fake_post)

    monkeypatch.setenv("BITRIX_STATE_PATH", str(state))
    monkeypatch.setenv("BITRIX_HTTP_TIMEOUT", "7")
    monkeypatch.setenv("BITRIX_HTTP_RETRIES", "2")
    monkeypatch.setattr(bx_client, "_http_session", lambda: FakeSession())
    monkeypatch.setattr(bx_client.time, "sleep", lambda _: None)

    response = bx_client.call("crm.deal.list")

    assert "slow handshake" in response["error"]
    assert attempts == [7, 7]


def test_call_syncs_and_retries_once_on_expired_token(monkeypatch, tmp_path):
    state = tmp_path / "install.latest.json"
    state.write_text(
        '{"payload":{"auth[client_endpoint]":"https://example.test/rest","auth[access_token]":"old-token"}}'
    )
    posts = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class FakeSession:
        def post(self, url, data=None, timeout=None):
            posts.append(data)
            if len(posts) == 1:
                return FakeResponse({"error": "expired_token"})
            return FakeResponse({"result": [{"ID": "1"}]})

    def fake_sync():
        state.write_text(
            '{"payload":{"auth[client_endpoint]":"https://example.test/rest","auth[access_token]":"new-token"}}'
        )

    monkeypatch.setenv("BITRIX_STATE_PATH", str(state))
    monkeypatch.setattr(bx_client, "_http_session", lambda: FakeSession())
    monkeypatch.setattr(bx_client, "ensure_token_fresh", fake_sync)

    response = bx_client.call("crm.deal.list")

    assert response == {"result": [{"ID": "1"}]}
    assert len(posts) == 2
    assert "auth=old-token" in posts[0]
    assert "auth=new-token" in posts[1]


def test_fetch_all_raises_on_bitrix_error(monkeypatch):
    monkeypatch.setattr(bx_client, "call", lambda method, params=None: {"error": "expired_token"})

    with pytest.raises(RuntimeError):
        bx_client.fetch_all("crm.deal.list")


def test_collect_users_and_photos_one_call_per_user():
    class Bx:
        def __init__(self):
            self.n = 0

        def call(self, method, params=None):
            self.n += 1
            return {"result": [{"ID": "1", "LAST_NAME": "Иванов", "NAME": "Иван"}]}

    bx = Bx()
    names, photos, roles = collect_users_and_photos({"1", "0", None}, bx)

    assert names == {"1": "Иванов Иван"}
    assert photos == {}
    assert roles == {}
    assert bx.n == 1  # один user.get на пользователя, не два (имя+фото из одного ответа)


def test_collect_users_collects_role_from_work_position():
    class Bx:
        def call(self, method, params=None):
            return {"result": [{"ID": "1", "LAST_NAME": "Гордиенко", "NAME": "Евгения",
                                 "WORK_POSITION": "РОП продаж"}]}

    names, photos, roles = collect_users_and_photos({"1"}, Bx())
    assert roles == {"1": "РОП продаж"}


def test_photo_store_read_first_without_bitrix(tmp_path, monkeypatch):
    from io import BytesIO
    from PIL import Image
    from src import collect

    monkeypatch.setenv("SCC_PHOTO_DIR", str(tmp_path))
    Image.new("RGB", (300, 300), (10, 120, 80)).save(tmp_path / "1.jpg", format="JPEG")

    class Bx:  # без PERSONAL_PHOTO — фото должно прийти из хранилища
        def call(self, method, params=None):
            return {"result": [{"ID": "1", "LAST_NAME": "Иванов", "NAME": "Иван"}]}

    names, photos, roles = collect_users_and_photos({"1"}, Bx())
    assert photos["1"].startswith("data:image/jpeg;base64,")


def test_resize_jpeg_pillow_shrinks_and_caps_140():
    from io import BytesIO
    from PIL import Image
    from src import collect
    buf = BytesIO()
    Image.new("RGB", (1000, 1000), (120, 40, 200)).save(buf, format="PNG")
    big = buf.getvalue()
    out = collect._resize_jpeg_pillow(big)
    assert out and len(out) < len(big)  # сжалось
    assert max(Image.open(BytesIO(out)).size) <= 140  # 140px кап


def test_compute_messenger_dialogs_per_manager_for_day():
    from src.collect import compute_messenger_dialogs
    wazzup = {
        "100": [{"CREATED": "2026-05-29T10:00:00+03:00"}],  # сегодня
        "200": [{"CREATED": "2026-05-20T10:00:00+03:00"}],  # старое — не считаем
        "300": [{"CREATED": "2026-05-29T15:00:00+03:00"}],
    }
    deal_manager = {"100": "1", "200": "1", "300": "2", "999": "1"}
    d0, d1 = "2026-05-29T00:00:00+03:00", "2026-05-29T23:59:59+03:00"
    out = compute_messenger_dialogs(wazzup, deal_manager, d0, d1)
    assert out == {"1": 1, "2": 1}
