#!/usr/bin/env python3
"""Чистка карточек «две организации в одной» (группа A) — удаление чужих реквизитов.

Разбор 22.06.2026. По каждой карточке оставляем правильное юрлицо, удаляем чужой
реквизит (добавлен позже кривым обогащением, не совпадает с сайтом/сделками/названием).

ВНИМАНИЕ: удаление реквизита в Bitrix необратимо (не корзина). Поэтому перед удалением
скрипт логирует ИНН/ОГРН/название — данные публичные, восстановимы вручную при ошибке.

#17504 (АО «ММК» / ООО «CDI», сайт International SOS) НЕ включён — не разрешён, нужен
ручной выбор клиента.

Запуск: python3 scripts/clean_groupA_requisites.py
"""
import json, urllib.parse, urllib.request, urllib.error

STATE = "shared/config/bitrix24-state/install.latest.json"
s = json.loads(open(STATE).read())["payload"]
endpoint = s["auth[client_endpoint]"].rstrip("/")
token = s["auth[access_token]"]


def call(method, params):
    url = f"{endpoint}/{method}"
    data = urllib.parse.urlencode([("auth", token), *params]).encode()
    for _ in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode())
            except Exception:
                return {}
        except Exception:
            continue
    return {}


# company_id -> (что оставляем, [req_id чужаков на удаление])
PLAN = {
    16704: ("СОФАРМА РУС (9705209745)",       [21978]),         # чужак: ЗЕНТИВА ФАРМА
    13388: ("КРЕДИТИТ (9710013385)",          [16718]),         # чужак: Ё-КРЕДИТ (Магадан)
    5004:  ("ИП Медведь (req 20462)",         [7928, 20454]),   # чужак: АВК БОШ АВТО СЕРВИС (оба)
    22944: ("ИП Камашева (req 13296)",        [12918, 13132]),  # чужак: ООО «БЕЗ НАЗВАНИЯ» (оба)
    9918:  ("ОСМ / os-med.ru (7801668681)",   [6066]),          # чужак: МЕДЦЕНТР ОСМЕД (Сочи)
    23076: ("ТРАНСНАВИСОФТ (7734362462)",     [13052]),         # чужак: ТРНС (Томск) — trnsoft.ru = ТРАНСНАВИСОФТ
}

for cid, (keep, reqids) in PLAN.items():
    print(f"=== #{cid}  оставляем: {keep} ===")
    for rid in reqids:
        r = call("crm.requisite.get", [("id", str(rid))]).get("result", {})
        print(f"  УДАЛЯЮ reqID={rid}: ИНН={r.get('RQ_INN')} ОГРН={r.get('RQ_OGRN')} «{r.get('RQ_COMPANY_NAME')}»")
        res = call("crm.requisite.delete", [("id", str(rid))])
        print(f"    -> {res.get('result', res.get('error_description'))}")
    left = call("crm.requisite.list", [("filter[ENTITY_TYPE_ID]", "4"), ("filter[ENTITY_ID]", str(cid)),
        ("select[]", "ID"), ("select[]", "RQ_INN"), ("select[]", "RQ_COMPANY_NAME")]).get("result", [])
    print(f"  ОСТАЛОСЬ: {[(x['ID'], x.get('RQ_INN'), x.get('RQ_COMPANY_NAME')) for x in left]}\n")

print("Готово. Примечание: у #23076 название карточки всё ещё «ООО ТРНС» — "
      "при желании переименуй в «ТРАНСНАВИСОФТ» вручную (это просто ярлык).")
