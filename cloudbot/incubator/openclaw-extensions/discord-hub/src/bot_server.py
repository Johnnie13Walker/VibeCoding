import os
from typing import Any

from flask import Flask, jsonify, request
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from common import Config, api_get_json


app = Flask(__name__)


def verify_signature(req) -> bool:
    signature = req.headers.get("X-Signature-Ed25519")
    timestamp = req.headers.get("X-Signature-Timestamp")
    if not signature or not timestamp:
        return False

    if not Config.discord_public_key:
        return False

    try:
        verify_key = VerifyKey(bytes.fromhex(Config.discord_public_key))
        verify_key.verify(f"{timestamp}{req.get_data(as_text=True)}".encode(), bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError):
        return False


def response_message(content: str) -> dict[str, Any]:
    return {"type": 4, "data": {"content": content}}


@app.post("/interactions")
def interactions():
    if not verify_signature(request):
        return jsonify({"error": "invalid request signature"}), 401

    payload = request.get_json(force=True, silent=False)
    if payload.get("type") == 1:
        return jsonify({"type": 1})

    data = payload.get("data", {})
    command_name = data.get("name")

    if command_name == "kpi":
        kpi = api_get_json("/kpi/summary")
        return jsonify(response_message(format_kpi(kpi)))

    if command_name == "alerts":
        alerts = api_get_json("/alerts/recent", {"limit": 5})
        return jsonify(response_message(format_alerts(alerts)))

    if command_name == "client":
        client_id = get_option(data, "client_id")
        if not client_id:
            return jsonify(response_message("Передайте параметр client_id"))
        client = api_get_json(f"/clients/{client_id}/summary")
        return jsonify(response_message(format_client(client)))

    return jsonify(response_message("Неизвестная команда"))


def get_option(data: dict[str, Any], name: str) -> str | None:
    for option in data.get("options", []):
        if option.get("name") == name:
            value = option.get("value")
            return str(value) if value is not None else None
    return None


def format_kpi(data: dict[str, Any]) -> str:
    title = data.get("title", "KPI summary")
    items = data.get("metrics", [])
    lines = [f"**{title}**"]
    for item in items[:10]:
        lines.append(f"- {item.get('name', 'metric')}: {item.get('value', 'n/a')}")
    return "\n".join(lines)


def format_alerts(data: dict[str, Any]) -> str:
    items = data.get("items", [])
    if not items:
        return "Активных алертов нет"
    lines = ["**Последние алерты**"]
    for item in items[:10]:
        sev = item.get("severity", "n/a")
        text = item.get("title", "alert")
        lines.append(f"- [{sev}] {text}")
    return "\n".join(lines)


def format_client(data: dict[str, Any]) -> str:
    name = data.get("name", "client")
    mrr = data.get("mrr", "n/a")
    health = data.get("health", "n/a")
    updated = data.get("updated_at", "n/a")
    return f"**Клиент:** {name}\nMRR: {mrr}\nHealth: {health}\nUpdated: {updated}"


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
