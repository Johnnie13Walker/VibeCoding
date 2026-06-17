#!/usr/bin/env bash
set -euo pipefail

TOKEN="<redacted_telegram_bot_token>"
CHAT_ID="<redacted_telegram_chat_id>"

# Moscow coordinates: 55.7558, 37.6176
JSON=$(curl -sS "https://api.open-meteo.com/v1/forecast?latitude=55.7558&longitude=37.6176&daily=weather_code,temperature_2m_max,temperature_2m_min&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,surface_pressure&timezone=Europe%2FMoscow")

TEXT=$(python3 - <<'PY' "$JSON"
import json, sys

def code_to_text(code: int) -> str:
    m = {
        0:"ясно",1:"преимущественно ясно",2:"переменная облачность",3:"пасмурно",
        45:"туман",48:"изморозь",51:"морось",53:"морось",55:"сильная морось",
        61:"небольшой дождь",63:"дождь",65:"сильный дождь",66:"ледяной дождь",67:"сильный ледяной дождь",
        71:"небольшой снег",73:"снег",75:"сильный снег",77:"снежные зёрна",
        80:"ливень",81:"ливень",82:"сильный ливень",85:"снежный ливень",86:"сильный снежный ливень",
        95:"гроза",96:"гроза с градом",99:"сильная гроза с градом"
    }
    return m.get(code, f"код {code}")

def outfit_advice(temp, feels, wind, weather_code):
    t = feels if feels is not None else temp
    tips = []

    if t is None:
        return ["Одевайтесь по сезону, ориентируясь на текущую температуру."]

    if t <= -15:
        tips.append("Очень холодно: тёплая зимняя куртка, термобельё, шапка, шарф и перчатки обязательны.")
    elif t <= -7:
        tips.append("Морозно: утеплённая куртка/пуховик, шапка и перчатки, обувь с тёплым носком.")
    elif t <= 0:
        tips.append("Холодно: тёплая куртка, свитер и закрытая обувь.")
    elif t <= 8:
        tips.append("Прохладно: демисезонная куртка и слой под низ (худи/свитер).")
    elif t <= 16:
        tips.append("Комфортно-прохладно: лёгкая куртка или плотная кофта.")
    elif t <= 24:
        tips.append("Тёплая погода: достаточно лёгкой одежды, можно взять тонкую ветровку на вечер.")
    else:
        tips.append("Жарко: лёгкая дышащая одежда, головной убор и вода с собой.")

    if wind is not None and wind >= 8:
        tips.append("Ветрено: добавьте ветрозащитный слой.")

    if weather_code in {51,53,55,61,63,65,66,67,80,81,82}:
        tips.append("Возможны осадки: возьмите зонт или непромокаемую куртку.")
    if weather_code in {71,73,75,77,85,86}:
        tips.append("Снег: выбирайте нескользящую и непромокаемую обувь.")

    return tips

data=json.loads(sys.argv[1])
cur=data.get("current",{})
day=data.get("daily",{})

max_t=(day.get("temperature_2m_max") or [None])[0]
min_t=(day.get("temperature_2m_min") or [None])[0]
weather_code=int(cur.get("weather_code",0))
weather=code_to_text(weather_code)
now_t=cur.get("temperature_2m")
feel=cur.get("apparent_temperature")
wind=cur.get("wind_speed_10m")
pressure=cur.get("surface_pressure")

advice = outfit_advice(now_t, feel, wind, weather_code)
advice_block = "\n".join([f"- {x}" for x in advice])

msg = (
    "🌤 Доброе утро! Погода в Москве\n\n"
    f"📍 Сейчас: {now_t}°C (ощущается как {feel}°C)\n"
    f"☁️ Условия: {weather}\n"
    f"🌡 Диапазон на день: {min_t}°C ... {max_t}°C\n"
    f"💨 Ветер: {wind} м/с\n"
    f"🧭 Давление: {pressure} гПа\n\n"
    "👕 Как лучше одеться:\n"
    f"{advice_block}"
)

print(msg)
PY
)

curl -sS -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "text=${TEXT}" >/tmp/send_moscow_weather.last.json

echo "sent"
