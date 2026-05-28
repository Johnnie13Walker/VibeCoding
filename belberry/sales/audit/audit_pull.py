#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_pull.py — параметрический пуллер аудита из Яндекс.Метрики (v1, движок Belberry).

Использование:
  python3 audit_pull.py --counter 100600199 --brand "панаце,panace,ариадна" [--months 12] [--json out.json]

Токен берётся из env METRIKA_OAUTH_TOKEN или из
~/.config/vibecoding/assistant/secrets/metrika-belberry.env

На выходе: нормализованный JSON (трафик, источники, заявки, бренд/небренд, страницы,
устройства) + health-score по дименшенам + флаг возможности допродажи.
"""
import argparse, json, os, sys, urllib.request, urllib.parse, urllib.error, datetime, re

ENVPATH = os.path.expanduser("~/.config/vibecoding/assistant/secrets/metrika-belberry.env")

def load_token():
    t = os.environ.get("METRIKA_OAUTH_TOKEN")
    if t: return t
    if os.path.exists(ENVPATH):
        for line in open(ENVPATH):
            if line.startswith("METRIKA_OAUTH_TOKEN="):
                return line.split("=",1)[1].strip()
    sys.exit("Нет токена: задай METRIKA_OAUTH_TOKEN или env-файл")

TOKEN = load_token()

def api(path, params):
    url = "https://api-metrika.yandex.net" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "OAuth " + TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "body": e.read().decode()[:300]}

def stat(cid, d1, d2, metrics, dims=None, filters=None, limit=200):
    # на больших счётчиках "full" даёт "Query is too complicated" -> откат к семплированию
    r=None
    for acc in ("full","medium","low","0.1"):
        p = {"ids": cid, "date1": d1, "date2": d2, "metrics": metrics, "accuracy": acc, "limit": limit}
        if dims: p["dimensions"] = dims
        if filters: p["filters"] = filters
        r = api("/stat/v1/data", p)
        if "__err" not in r: 
            r["_accuracy"]=acc; return r
        if r.get("__err")!=400 or "complicated" not in str(r.get("body","")): return r
    return r

LEAD_TYPES = {"form", "contact_data", "contact_data_sent", "phone", "button"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--counter", required=True)
    ap.add_argument("--brand", default="", help="бренд-термины через запятую (важно для бренд/небренд)")
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    cid = a.counter
    today = datetime.date.today().replace(day=1)
    d2 = (today - datetime.timedelta(days=1))
    d1 = (today - datetime.timedelta(days=1))
    # период: последние N полных месяцев
    m = today
    for _ in range(a.months):
        m = (m - datetime.timedelta(days=1)).replace(day=1)
    D1, D2 = m.isoformat(), d2.isoformat()

    out = {"counter": cid, "period": [D1, D2]}

    # мета счётчика
    meta = api(f"/management/v1/counter/{cid}", {})
    c = meta.get("counter", {})
    out["site"] = c.get("site"); out["name"] = c.get("name")
    domain_stem = re.sub(r"^www\.", "", (c.get("site") or "")).split(".")[0].lower()
    brand_terms = [b.strip().lower() for b in a.brand.split(",") if b.strip()]
    if domain_stem and domain_stem not in brand_terms:
        brand_terms.append(domain_stem)
    out["brand_terms"] = brand_terms

    # сводка
    r = stat(cid, D1, D2, "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds")
    if "__err" in r: sys.exit(f"Метрика недоступна: {r}")
    t = r["totals"]
    out["summary"] = {"visits": t[0], "users": t[1], "bounce": round(t[2],1), "depth": round(t[3],2), "dur_s": round(t[4])}

    # источники (визиты)
    r = stat(cid, D1, D2, "ym:s:visits", "ym:s:lastsignTrafficSource")
    src = {row["dimensions"][0]["name"]: row["metrics"][0] for row in r.get("data",[])}
    out["sources_visits"] = src
    organic = src.get("Search engine traffic", 0)
    out["organic_share"] = round(organic / max(t[0],1) * 100, 1)

    # цели → лид-цели
    g = api(f"/management/v1/counter/{cid}/goals", {})
    goals = g.get("goals", []) if "__err" not in g else []
    lead_goals = [gg for gg in goals if gg.get("type") in LEAD_TYPES]
    out["goals"] = [{"id": gg["id"], "name": gg.get("name"), "type": gg.get("type")} for gg in goals]
    # основная форма
    form_goal = next((gg for gg in goals if gg.get("type")=="form"), (lead_goals[0] if lead_goals else None))
    out["lead_goal_id"] = form_goal["id"] if form_goal else None

    # заявки по источнику + всего
    if form_goal:
        gid = form_goal["id"]
        r = stat(cid, D1, D2, f"ym:s:visits,ym:s:goal{gid}reaches", "ym:s:lastsignTrafficSource")
        leads_by_src = {}; total_leads = 0
        for row in r.get("data",[]):
            leads_by_src[row["dimensions"][0]["name"]] = row["metrics"][1]
            total_leads += row["metrics"][1]
        out["leads_total"] = total_leads
        out["leads_by_source"] = leads_by_src

        # бренд/небренд по фразам органики
        r = stat(cid, D1, D2, f"ym:s:goal{gid}reaches", "ym:s:searchPhrase",
                 filters="ym:s:lastsignTrafficSource=='organic'", limit=300)
        brand=nonbrand=0; nb_examples=[]
        for row in r.get("data",[]):
            ph = (row["dimensions"][0]["name"] or "").lower(); f = row["metrics"][0]
            if f <= 0 or not ph or "не определено" in ph: continue
            if any(b in ph for b in brand_terms): brand += f
            else:
                nonbrand += f
                if len(nb_examples) < 10: nb_examples.append((ph, f))
        out["organic_leads_brand"] = brand
        out["organic_leads_nonbrand"] = nonbrand
        out["nonbrand_examples"] = nb_examples

    # страницы входа по заявкам
    if form_goal:
        r = stat(cid, D1, D2, f"ym:s:goal{form_goal['id']}reaches", "ym:s:startURLPath", limit=15)
        out["leads_by_page"] = [(row["dimensions"][0]["name"], row["metrics"][0]) for row in r.get("data",[]) if row["metrics"][0]>0][:10]

    # устройства
    r = stat(cid, D1, D2, "ym:s:visits", "ym:s:deviceCategory")
    out["devices"] = {row["dimensions"][0]["name"]: row["metrics"][0] for row in r.get("data",[])}

    # ---- HEALTH-SCORE (0-100 по дименшенам) ----
    s = {}
    # 1. Независимость привлечения: доля небрендовых заявок (из заявок с известной фразой)
    known = out.get("organic_leads_brand",0) + out.get("organic_leads_nonbrand",0)
    nb_share = (out.get("organic_leads_nonbrand",0)/known*100) if known else 0
    out["nonbrand_lead_share"] = round(nb_share,1)
    s["acquisition_independence"] = round(min(nb_share/40*100,100))  # 40%+ небренда = отлично
    # 2. Органика как канал
    s["organic_strength"] = round(min(out["organic_share"]/40*100,100))
    # 3. Конверсия визит→заявка
    cr = (out.get("leads_total",0)/max(t[0],1)*100)
    out["lead_cr"] = round(cr,2)
    s["conversion"] = round(min(cr/3*100,100))  # 3%+ = отлично
    # 4. Вовлечённость (низкий отказ + глубина)
    s["engagement"] = round(max(0, min((100-out["summary"]["bounce"]) ,100)))
    # 5. Зрелость измерения (число типов целей)
    gtypes = len(set(gg.get("type") for gg in goals))
    s["measurement"] = round(min(gtypes/4*100,100))
    out["scores"] = s
    out["health_score"] = round(sum(s.values())/len(s)) if s else 0
    # флаг возможности: много трафика + мало небрендовых лидов = жертва «перехвата»
    out["opportunity_flag"] = (out["summary"]["visits"]>3000 and nb_share<25)

    js = json.dumps(out, ensure_ascii=False, indent=2)
    if a.json:
        open(a.json,"w",encoding="utf-8").write(js)

    # человекочитаемая сводка
    print(f"=== {out['name']} ({out['site']}) · счётчик {cid} ===")
    print(f"период {D1}…{D2}")
    print(f"визиты {out['summary']['visits']:.0f} · органика {out['organic_share']}% · отказы {out['summary']['bounce']}%")
    print(f"заявки {out.get('leads_total',0):.0f} · CR {out.get('lead_cr',0)}%")
    if known:
        print(f"органик-заявки: БРЕНД {out['organic_leads_brand']:.0f} / НЕБРЕНД {out['organic_leads_nonbrand']:.0f} (небренд {out['nonbrand_lead_share']}%)")
        print(f"  небренд-примеры: {', '.join(p for p,_ in out['nonbrand_examples'][:5]) or '—'}")
    print(f"устройства: {out['devices']}")
    print(f"SCORES: {s}")
    print(f"HEALTH {out['health_score']}/100 · {'⚑ КАНДИДАТ НА ДОПРОДАЖУ' if out['opportunity_flag'] else 'ok'}")

if __name__ == "__main__":
    main()
