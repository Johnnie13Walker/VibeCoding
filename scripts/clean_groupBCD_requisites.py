#!/usr/bin/env python3
"""Чистка чужих реквизитов в группах B/C (уверенная часть). Разбор 23.06.2026.

Удаляем только там, где правильное юрлицо однозначно (структурно/сайт/гео/TITLE).
Спорные (две одноимённые, ИП-двойники, неоднозначный домен) — НЕ трогаем, см. флаг
в отчёте. Удаление реквизита необратимо → логируем ИНН/ОГРН/название перед удалением.

Запуск: python3 scripts/clean_groupBCD_requisites.py
"""
import json, urllib.parse, urllib.request, urllib.error

STATE = "shared/config/bitrix24-state/install.latest.json"
s = json.loads(open(STATE).read())["payload"]
endpoint = s["auth[client_endpoint]"].rstrip("/")
token = s["auth[access_token]"]


def call(method, params):
    data = urllib.parse.urlencode([("auth", token), *params]).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{endpoint}/{method}", data=data), timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


# company_id -> (что оставляем, [req_id чужаков], причина)
PLAN = {
    2872:  ("ООО Омега Москва 7724430265",       [3298],  "сайт=ООО Омега Талдомская(86.10); убираем Оренбург-стоматологию"),
    14282: ("ДЕТСКИЕ ПРАЗДНИКИ ООО 1515915762", [4990],  "удаляем 12-зн ИНН на ООО"),
    24153: ("ГРУППА ДИНАМИКА 7751019294",       [14723], "удаляем 12-зн ИНН на ООО"),
    4904:  ("Д-Р ЭСТЕТИК 9709050953",           [24964], "точный дубль реквизита"),
    3768:  ("ООО МЕДСКАН 7725819008",           [3268],  "подвал сайта = ООО МЕДСКАН; убираем АО"),
    14896: ("ЭСТЕТИКА Хабаровск 2721229390",    [4838],  "сайт estetika-khv = Хабаровск; убираем Саратов"),
    17712: ("ФИРМА ОРИС 7728784681",            [2936],  "сайт orisfirm = ФИРМА ОРИС; убираем ОРИС МЕД"),
    12498: ("ЗАВОД РАДИОПРИБОР 7810241293",     [5506],  "сайт zrp + TITLE = Радиоприбор; убираем АО СРЗ"),
    20364: ("КЛИНИКА ЭКСПЕРТ СТОЛИЦА 7730293338", [10048], "сайт msk + TITLE = Столица; убираем СПб Поликлинику"),
    5518:  ("СТОЛИЧНАЯ СТОМАТОЛОГИЯ М 9731061527", [7510], "TITLE = …М (Москва); убираем Чувашию"),
    14750: ("ТД СУВЕНИР 1215181711",            [4872],  "TITLE = ТД СУВЕНИР; убираем Первую сувенирную"),
    15566: ("ИП Александров СПб 780530316754",  [4564],  "реестр: СПб галантерея 47.51.2 = jeterini.ru; убираем Белгород-двойника"),
    3878:  ("ООО ЛИЦА СПб 7804592286",          [7866],  "реестр: Ижевск ИНН — склады 52.10 (чужак); оставляем СПб салоны красоты"),
    22452: ("ООО МЕБИУСПРО 7734432102",         [12248], "реестр: МЕБИУСГРУПП ликвидирован 06.08.2025; оставляем действующий ПРО (=TITLE)"),
}

for cid, (keep, reqids, why) in PLAN.items():
    print(f"=== #{cid}  оставляем: {keep}  ({why}) ===")
    for rid in reqids:
        r = call("crm.requisite.get", [("id", str(rid))]).get("result", {})
        ogrn = r.get("RQ_OGRN") or r.get("RQ_OGRNIP") or ""
        print(f"  УДАЛЯЮ reqID={rid}: ИНН={r.get('RQ_INN')} ОГРН={ogrn} «{r.get('RQ_COMPANY_NAME')}»")
        res = call("crm.requisite.delete", [("id", str(rid))])
        print(f"    -> {res.get('result', res.get('error_description'))}")
    left = call("crm.requisite.list", [("filter[ENTITY_TYPE_ID]", "4"), ("filter[ENTITY_ID]", str(cid)),
        ("select[]", "ID"), ("select[]", "RQ_INN"), ("select[]", "RQ_COMPANY_NAME")]).get("result", [])
    print(f"  ОСТАЛОСЬ: {[(x['ID'], x.get('RQ_INN'), x.get('RQ_COMPANY_NAME')) for x in left]}\n")
