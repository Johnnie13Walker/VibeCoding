#!/usr/bin/env python3
"""Анализ воронки [10] Продажи Belberry по выгруженным JSON. Только чтение/расчёт."""
import json, statistics as st
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from pathlib import Path

D = Path("/tmp/funnel_analysis")
NOW = datetime(2026, 6, 17, tzinfo=timezone(timedelta(hours=3)))
def L(n): return json.load(open(D/n))

def pdt(s):
    if not s: return None
    try: return datetime.fromisoformat(s)
    except: return None

users = {str(u["ID"]): f'{u.get("LAST_NAME") or ""} {u.get("NAME") or ""}'.strip() or u["ID"] for u in L("users.json")}
active = {str(u["ID"]): (u.get("ACTIVE") in (True,"true","Y",1)) for u in L("users.json")}
sources = {s["STATUS_ID"]: s["NAME"] for s in L("sources.json")}
uf = {f["FIELD_NAME"]: f for f in L("deal_userfields.json")}
reason10 = {str(i["ID"]): i["VALUE"] for i in (uf.get("UF_CRM_1771495464",{}).get("LIST") or [])}

STAGES10 = {
 "C10:NEW":"1.Квалификация","C10:PREPAYMENT_INVOIC":"2.Подготовка БРИФа","C10:EXECUTING":"3.Подготовка КП",
 "C10:FINAL_INVOICE":"4.Догрев и переговоры","C10:UC_KC7195":"5.Подготовка договора",
 "C10:WON":"WON","C10:LOSE":"LOSE","C10:1":"ОТЛОЖЕНО"}
ORDER = ["C10:NEW","C10:PREPAYMENT_INVOIC","C10:EXECUTING","C10:FINAL_INVOICE","C10:UC_KC7195","C10:WON"]

deals12 = L("deals_cat10_12m.json")
open10 = L("deals_cat10_open.json")
# объединим открытые (могут быть старше 12м) в общий словарь по ID
by_id = {str(d["ID"]): d for d in deals12}
for d in open10: by_id.setdefault(str(d["ID"]), d)

def f(v):
    try: return float(v or 0)
    except: return 0.0

print("="*80); print("РАЗДЕЛ A. ОБЩИЕ МЕТРИКИ — воронка [10] Продажи, окно 12 мес (с 2025-06-17)"); print("="*80)
won=[d for d in deals12 if d["STAGE_ID"]=="C10:WON"]
lose=[d for d in deals12 if d["STAGE_ID"]=="C10:LOSE"]
defer=[d for d in deals12 if d["STAGE_ID"]=="C10:1"]
opn=[d for d in deals12 if d.get("CLOSED")=="N"]
ytd=[d for d in deals12 if (pdt(d["DATE_CREATE"]) or NOW) >= datetime(2026,1,1,tzinfo=timezone(timedelta(hours=3)))]
ytd_won=[d for d in ytd if d["STAGE_ID"]=="C10:WON"]
ytd_lose=[d for d in ytd if d["STAGE_ID"]=="C10:LOSE"]
print(f"Создано сделок 12м: {len(deals12)} | сумма pipeline: {sum(f(d['OPPORTUNITY']) for d in deals12):,.0f} ₽")
print(f"  WON: {len(won)} на {sum(f(d['OPPORTUNITY']) for d in won):,.0f} ₽")
print(f"  LOSE: {len(lose)} на {sum(f(d['OPPORTUNITY']) for d in lose):,.0f} ₽")
print(f"  ОТЛОЖЕНО: {len(defer)} на {sum(f(d['OPPORTUNITY']) for d in defer):,.0f} ₽")
print(f"  открытых (из окна): {len(opn)}")
closed = len(won)+len(lose)
print(f"Конверсия в продажу (WON / (WON+LOSE), без отложенных): {100*len(won)/closed:.1f}%" if closed else "нет закрытых")
if won: print(f"Средний чек WON: {sum(f(d['OPPORTUNITY']) for d in won)/len(won):,.0f} ₽ | медиана: {st.median([f(d['OPPORTUNITY']) for d in won]):,.0f} ₽")
# длительность сделки WON/LOSE
def dur(d):
    a=pdt(d.get("DATE_CREATE")); b=pdt(d.get("CLOSEDATE"))
    return (b-a).days if a and b and b>=a else None
won_dur=[x for x in (dur(d) for d in won) if x is not None]
lose_dur=[x for x in (dur(d) for d in lose) if x is not None]
if won_dur: print(f"Цикл сделки WON: средн {st.mean(won_dur):.0f} дн, медиана {st.median(won_dur):.0f} дн")
if lose_dur: print(f"Цикл до LOSE: средн {st.mean(lose_dur):.0f} дн, медиана {st.median(lose_dur):.0f} дн")
print(f"\nYTD (с 2026-01-01): создано {len(ytd)}, WON {len(ytd_won)} на {sum(f(d['OPPORTUNITY']) for d in ytd_won):,.0f} ₽, LOSE {len(ytd_lose)}")
clo=len(ytd_won)+len(ytd_lose)
print(f"  YTD конверсия: {100*len(ytd_won)/clo:.1f}%" if clo else "  YTD нет закрытых")

print("\n"+"="*80); print("РАЗДЕЛ B. ВОРОНКА ПО СТАДИЯМ (история стадий, окно 12м)"); print("="*80)
sh=[h for h in L("stagehistory_cat10.json")]
# для каждой сделки 12м — какие стадии она посетила, и время между переходами
sh_by_owner=defaultdict(list)
for h in sh:
    sh_by_owner[str(h["OWNER_ID"])].append(h)
for o in sh_by_owner: sh_by_owner[o].sort(key=lambda x: x["CREATED_TIME"])
ids12=set(by_id.keys())
visited=Counter();
for oid,hs in sh_by_owner.items():
    if oid not in ids12: continue
    for st_ in set(h["STAGE_ID"] for h in hs):
        visited[st_]+=1
print("Сколько сделок (из окна) КОГДА-ЛИБО были на стадии (по истории):")
for s in ORDER+["C10:LOSE","C10:1"]:
    print(f"  {STAGES10.get(s,s):24} посетило {visited.get(s,0)}")
# текущее распределение открытых
print("\nТекущее распределение ОТКРЫТЫХ сделок [10] (все открытые, не только 12м):")
cur=Counter(d["STAGE_ID"] for d in open10)
cur_sum=defaultdict(float)
for d in open10: cur_sum[d["STAGE_ID"]]+=f(d["OPPORTUNITY"])
for s in ORDER[:-1]+["C10:1"]:
    print(f"  {STAGES10.get(s,s):24} {cur.get(s,0):3} шт | {cur_sum.get(s,0):,.0f} ₽")
# межстадийная конверсия по истории (доля сделок дошедших до стадии N+1 среди дошедших до N)
print("\nМежстадийная конверсия (по истории, окно сделок 12м):")
reached=defaultdict(set)
for oid,hs in sh_by_owner.items():
    if oid not in ids12: continue
    for h in hs: reached[h["STAGE_ID"]].add(oid)
for i in range(len(ORDER)-1):
    a,b=ORDER[i],ORDER[i+1]
    na=len(reached[a]); nb=len(reached[b])
    print(f"  {STAGES10.get(a):24} -> {STAGES10.get(b):24}: {na}->{nb} = {100*nb/na:.0f}%" if na else f"  {a} нет данных")
# время на стадии: по последовательным переходам внутри owner
print("\nСреднее/медианное время НА стадии (дни, по парам переходов, окно 12м):")
stage_times=defaultdict(list)
for oid,hs in sh_by_owner.items():
    if oid not in ids12: continue
    for j in range(len(hs)-1):
        t0=pdt(hs[j]["CREATED_TIME"]); t1=pdt(hs[j+1]["CREATED_TIME"])
        if t0 and t1 and t1>=t0:
            stage_times[hs[j]["STAGE_ID"]].append((t1-t0).days)
for s in ORDER[:-1]:
    v=stage_times.get(s,[])
    if v: print(f"  {STAGES10.get(s):24} n={len(v):3} средн {st.mean(v):5.1f} медиана {st.median(v):5.1f} макс {max(v)}")

print("\n"+"="*80); print("РАЗДЕЛ C. ПРИЧИНЫ ОТКАЗА (LOSE, 12м)"); print("="*80)
rc=Counter(); rc_sum=defaultdict(float); empty=0
for d in lose:
    r=str(d.get("UF_CRM_1771495464") or "").strip()
    if not r or r=="None": empty+=1; r="(пусто)"
    name=reason10.get(r, r if r=="(пусто)" else f"id={r}")
    rc[name]+=1; rc_sum[name]+=f(d["OPPORTUNITY"])
print(f"Всего LOSE: {len(lose)}, без причины/пусто: {empty} ({100*empty/len(lose):.0f}%)" if lose else "нет LOSE")
for name,cnt in rc.most_common():
    print(f"  {name:48} {cnt:3} шт | потеря {rc_sum[name]:,.0f} ₽")

print("\n"+"="*80); print("РАЗДЕЛ D. МЕНЕДЖЕРЫ (12м, воронка 10)"); print("="*80)
mgr=defaultdict(lambda: {"all":0,"won":0,"lose":0,"open":0,"won_sum":0.0,"durs":[]})
for d in deals12:
    m=str(d["ASSIGNED_BY_ID"]); s=d["STAGE_ID"]
    mgr[m]["all"]+=1
    if s=="C10:WON": mgr[m]["won"]+=1; mgr[m]["won_sum"]+=f(d["OPPORTUNITY"]);
    if s=="C10:LOSE": mgr[m]["lose"]+=1
    if d.get("CLOSED")=="N": mgr[m]["open"]+=1
    dd=dur(d)
    if s=="C10:WON" and dd is not None: mgr[m]["durs"].append(dd)
print(f"{'Менеджер':22}{'всего':>6}{'WON':>5}{'LOSE':>5}{'откр':>5}{'конв%':>7}{'выручка':>14}{'цикл':>6}")
for m,v in sorted(mgr.items(), key=lambda x:-x[1]["won_sum"]):
    cl=v["won"]+v["lose"]; conv=100*v["won"]/cl if cl else 0
    cyc=f"{st.median(v['durs']):.0f}" if v["durs"] else "-"
    print(f"{users.get(m,m)[:21]:22}{v['all']:>6}{v['won']:>5}{v['lose']:>5}{v['open']:>5}{conv:>6.0f}%{v['won_sum']:>14,.0f}{cyc:>6}")

print("\n"+"="*80); print("РАЗДЕЛ E. ИСТОЧНИКИ (12м, воронка 10)"); print("="*80)
src=defaultdict(lambda: {"all":0,"won":0,"lose":0,"won_sum":0.0})
for d in deals12:
    s=sources.get(d.get("SOURCE_ID"), d.get("SOURCE_ID") or "(пусто)")
    src[s]["all"]+=1
    if d["STAGE_ID"]=="C10:WON": src[s]["won"]+=1; src[s]["won_sum"]+=f(d["OPPORTUNITY"])
    if d["STAGE_ID"]=="C10:LOSE": src[s]["lose"]+=1
print(f"{'Источник':30}{'всего':>6}{'WON':>5}{'LOSE':>5}{'конв%':>7}{'выручка':>14}")
for s,v in sorted(src.items(), key=lambda x:-x[1]["all"]):
    cl=v["won"]+v["lose"]; conv=100*v["won"]/cl if cl else 0
    print(f"{str(s)[:29]:30}{v['all']:>6}{v['won']:>5}{v['lose']:>5}{conv:>6.0f}%{v['won_sum']:>14,.0f}")

print("\n"+"="*80); print("РАЗДЕЛ F. ПРОБЛЕМНЫЕ ЗОНЫ (открытые сделки [10], все)"); print("="*80)
stale=[]; noact=[]
for d in open10:
    la=pdt(d.get("LAST_ACTIVITY_TIME"));
    days=(NOW-la).days if la else 9999
    if days>=14: stale.append((days,d))
print(f"Открытых сделок: {len(open10)} на {sum(f(d['OPPORTUNITY']) for d in open10):,.0f} ₽")
print(f"Без активности ≥14 дней: {len(stale)} на {sum(f(d['OPPORTUNITY']) for _,d in stale):,.0f} ₽")
print("ТОП-15 зависших (дни без активности, сумма, стадия, менеджер):")
for days,d in sorted(stale, key=lambda x:-f(x[1]['OPPORTUNITY']))[:15]:
    dd="нет акт." if days==9999 else f"{days}д"
    print(f"  #{d['ID']:6} {dd:9} {f(d['OPPORTUNITY']):>12,.0f}₽ {STAGES10.get(d['STAGE_ID'],d['STAGE_ID']):24} {users.get(str(d['ASSIGNED_BY_ID']),'')[:20]}")
# высокая сумма без движения
print(f"\nОткрытые с суммой 0 (нет бюджета в карточке): {sum(1 for d in open10 if f(d['OPPORTUNITY'])==0)}")

print("\n"+"="*80); print("РАЗДЕЛ G. ТЕЛЕМАРКЕТИНГ [50] — фид воронки (12м)"); print("="*80)
tm=L("deals_cat50_12m.json")
tm_won=[d for d in tm if d["STAGE_ID"]=="C50:WON"]
tm_meet=[d for d in tm if d["STAGE_ID"]=="C50:UC_WZ4KQE"]
print(f"Создано в ТМ 12м: {len(tm)} | УСПЕХ(передано в продажи): {len(tm_won)} | на стадии 'Встреча назначена': {len(tm_meet)}")
print(f"ОТЛОЖЕНО: {sum(1 for d in tm if d['STAGE_ID']=='C50:LOSE')} | ОТВАЛ: {sum(1 for d in tm if d['STAGE_ID']=='C50:APOLOGY')}")
print(f"Конверсия ТМ в успех: {100*len(tm_won)/len(tm):.1f}%")
print("\nDONE")
