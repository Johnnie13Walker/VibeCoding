#!/usr/bin/env python3
"""KP-пайплайн MVP: сделка → данные аудитов → заготовка КП (SEO-Belberry).

Оркестрирует существующие скрипты движка (bitrix_audit / build_kp / metrika_audit /
prodoctorov_audit) в папке клиента, ведёт состояние стадий в kp_job.json
(идемпотентно: готовые стадии пропускаются), собирает kp_data.json — свод фактов
строго с источниками — и копирует эталон деки. Цены НЕ считает (зона сметчика),
в Bitrix НЕ пишет. Спека: KP-ENGINE-MVP-SPEC.md.

    python3 kp_pipeline.py <deal_id> [--client имя] [--competitors d1 d2 ...]
                           [--days 90] [--prodoctorov url ...]
                           [--skip-metrika] [--skip-prodoctorov]
                           [--status] [--force стадия|all]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

KP_DIR = Path(__file__).resolve().parent

# enum «Список услуг» брифа СП1056 → пресет сметы kp_smeta (тарифы матрицы)
BRIEF_SVC_TO_PRESET = {
    2730: "seo", 2726: "ppc", 2732: "orm", 2738: "program",
    2740: "lp", 2742: "branding", 2736: "tv",
}


def pick_template(brand: str = "belberry") -> Path:
    """Золотой шаблон деки по бренду; запасной вариант — клиентский эталон."""
    tpl = KP_DIR / "templates" / f"seo-{brand}"
    if (tpl / "kp.html").exists():
        return tpl
    return KP_DIR / "clients" / "med-shushary"


def preset_for_brief(brief_services: list | None, default: str = "seo") -> str:
    """Пресет сметы по услугам брифа: первая знакомая услуга, иначе default."""
    for svc in brief_services or []:
        if svc in BRIEF_SVC_TO_PRESET:
            return BRIEF_SVC_TO_PRESET[svc]
    return default


def deck_substitutions(data: dict, today: str) -> dict[str, str]:
    """Карта замен плейсхолдеров деки реальными фактами (только то, что знаем)."""
    facts = {f["key"]: f["value"] for f in data.get("facts", [])}
    subs: dict[str, str] = {}
    domain = data.get("domain") or ""
    if domain:
        subs["{{ДОМЕН}}"] = domain
        subs["{{домен}}"] = domain
        subs["{{КЛИЕНТ}}"] = str(facts.get("deal_title") or domain)
    subs["{{ДАТА}}"] = today
    region = facts.get("brief:Регион продвижения")
    if region:
        subs["{{ГОРОД}}"] = str(region)
        subs["{{ГЕО}}"] = str(region)
    services = facts.get("brief:Приоритетные товары/услуги, которые нужно продвигать")
    if services:
        subs["{{ПРИОРИТЕТНЫЕ_УСЛУГИ}}"] = str(services)
    return subs


def render_traffic_drop(data: dict) -> str | None:
    """HTML-фрагмент баннера просадки для маркера AUTO:TRAFFIC_DROP."""
    fact = next((f for f in data.get("facts", []) if f["key"] == "traffic_drop"), None)
    if not fact:
        return None
    # «пик 66500 (05.2024) → сейчас 16500 = -75%»
    txt = str(fact["value"])
    pct = txt.split("=")[-1].strip() if "=" in txt else ""
    return (f'<div class="pb-num">{pct}</div>\n'
            f'<div class="pb-txt"><b>Трафик из поиска просел.</b> {txt}. '
            f'Кривая идёт вниз — без работ просадка продолжится. '
            f'<span style="opacity:.7">[данные API-аудита]</span></div>')
STAGES = ["bitrix", "audit", "metrika", "prodoctorov", "assemble", "scaffold", "smeta"]

# Маркеры в kp.html эталона для автовставки (если их нет — оставляем файлы рядом)
MARK_BENCH = "<!--AUTO:SEO_BENCHMARK-->"
MARK_PROBLEMS = "<!--AUTO:PROBLEM_SOLUTION-->"
MARK_TRAFFIC = "<!--AUTO:TRAFFIC_DROP-->"

DOMAIN_RE = re.compile(r"\b((?:[a-zа-я0-9-]+\.)+(?:ru|com|net|org|рф|su|online|site|clinic|moscow|спб))\b",
                       re.IGNORECASE)


# ── pure-функции (покрыты тестами) ────────────────────────────────────────────

def domain_from_bitrix(bx: dict) -> str:
    """Домен клиента из bitrix.json: поле site сделки, затем бриф, затем TITLE."""
    cands = [bx.get("site") or "",
             (bx.get("brief") or {}).get("Адрес вашего сайта (SEO)") or "",
             bx.get("title") or ""]
    for c in cands:
        c = c.strip().lower()
        c = re.sub(r"^https?://", "", c)
        c = re.sub(r"^www\.", "", c).split("/")[0].strip()
        if "." in c and " " not in c:
            return c
    return ""


def competitors_from_brief(bx: dict, limit: int = 5) -> list[str]:
    """Домены конкурентов из текста брифа (поле со словом «конкурент»).

    Берём только то, что похоже на домен; «мир семьи, веда» текстом — не берём
    (сейлс передаст --competitors). Свой домен исключаем.
    """
    own = domain_from_bitrix(bx)
    text = " ".join(v for k, v in (bx.get("brief") or {}).items()
                    if "конкурент" in k.lower() and isinstance(v, str))
    seen, out = set(), []
    for m in DOMAIN_RE.finditer(text):
        d = m.group(1).lower().lstrip("www.")
        if d != own and d not in seen:
            seen.add(d)
            out.append(d)
    return out[:limit]


def plan_stages(job: dict, force: str | None = None,
                skip: set[str] | None = None) -> list[str]:
    """Какие стадии выполнять: не-done/skipped, минус пропущенные; force=имя|all сбрасывает."""
    skip = skip or set()
    done = {s for s, st in (job.get("stages") or {}).items()
            if st.get("status") in ("done", "skipped")}
    if force == "all":
        done = set()
    elif force:
        done.discard(force)
    return [s for s in STAGES if s not in done and s not in skip]


def traffic_dynamics(history: dict, current=None) -> dict | None:
    """Просадка трафика из visits_history PR-CY: пик → текущее → % падения.

    Слайд «остановить просадку» — главный аргумент SEO-КП. Ключи YYYYMM, нули
    игнорируем (PR-CY ставит 0 за месяцы без данных).
    """
    points = {m: v for m, v in (history or {}).items() if isinstance(v, (int, float)) and v > 0}
    if not points:
        return None
    peak_month, peak = max(points.items(), key=lambda kv: kv[1])
    cur = current if isinstance(current, (int, float)) and current > 0 else points[max(points)]
    if peak <= cur:
        return None
    ym = str(peak_month)
    return {"peak": int(peak), "peak_month": f"{ym[4:6]}.{ym[:4]}",
            "current": int(cur), "drop_pct": -round((peak - cur) / peak * 100)}


def assemble_kp_data(bitrix: dict | None, audit: dict | None,
                     metrika: dict | None, prodoc: list | None,
                     brand: str = "belberry") -> dict:
    """Свод фактов с источниками + чек-лист ручных шагов. Без источника — не факт."""
    facts, hypotheses = [], []

    def fact(key, value, source):
        if value is None or value == "":
            return
        facts.append({"key": key, "value": value, "source": source, "status": "факт"})

    if bitrix:
        fact("deal_title", bitrix.get("title"), "bitrix.json:deal")
        fact("company_revenue", bitrix.get("company_revenue"), "bitrix.json:deal")
        brief = bitrix.get("brief") or {}
        for k in ("Приоритетные товары/услуги, которые нужно продвигать",
                  "Регион продвижения", "Опишите вашу целевую аудиторию", "УТП и офферы"):
            fact(f"brief:{k}", brief.get(k), "bitrix.json:бриф СП1056")
    if audit:
        cl = audit.get("client") or {}
        if isinstance(cl, dict):
            for k in ("sqi", "yandex_index", "google_index", "organic_pct",
                      "bounce_rate", "visits_monthly", "load_time", "schema_org"):
                fact(k, cl.get(k), "audit.json:pr-cy")
            drop = traffic_dynamics(cl.get("visits_history") or {}, cl.get("visits_monthly"))
            if drop:
                fact("traffic_drop",
                     f"пик {drop['peak']} ({drop['peak_month']}) → сейчас {drop['current']} "
                     f"= {drop['drop_pct']}%", "audit.json:pr-cy:visits_history")
    if metrika:
        for k in ("visits", "users", "organic_share", "goals"):
            fact(f"metrika:{k}", metrika.get(k), "metrika.json")
    if prodoc:
        for i, c in enumerate(prodoc):
            if isinstance(c, dict):
                fact(f"prodoctorov:{i}:rating", c.get("rating"), "prodoctorov.json")
                fact(f"prodoctorov:{i}:reviews", c.get("reviews"), "prodoctorov.json")

    if not metrika:
        hypotheses.append({"key": "посещаемость", "status": "гипотеза",
                           "note": "Метрика недоступна — только оценка PR-CY; запросить гостевой доступ"})

    return {
        "deal_id": (bitrix or {}).get("deal_id"),
        "domain": domain_from_bitrix(bitrix or {}),
        "brand": "Acoola Team" if brand == "acoola" else "Belberry",
        "facts": facts,
        "hypotheses": hypotheses,
        "manual_checklist": [
            "Цены — только из сметы сметчика (Google Sheets по матрице), не выдумывать",
            "Титул: клиент, домен, дата, дедлайн подарка/скидки",
            "Каскад скидок: 10% логотип / 5% оперативность с датой (по правилам матрицы)",
            "Прогнозы — диапазоны + дисклеймер «оценка на текущий момент» (LEGAL-MED-2026 §2)",
            "Никаких гарантий результата и «случаев излечения» (ст. 24 ФЗ-38)",
            "Перед отправкой: в папке только клиентские файлы (без внутренних калькуляторов)",
        ],
    }


def inject_auto_blocks(kp_html: str, benchmark: str | None, problems: str | None) -> tuple[str, list[str]]:
    """Вставка авто-фрагментов по маркерам. Возвращает (html, что_не_вставлено)."""
    missing = []
    for mark, frag, name in ((MARK_BENCH, benchmark, "seo_benchmark"),
                             (MARK_PROBLEMS, problems, "problem_solution")):
        if frag and mark in kp_html:
            kp_html = kp_html.replace(mark, frag)
        elif frag:
            missing.append(name)
    return kp_html, missing


# ── исполнение стадий ─────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _run(script: str, args: list[str], cwd: Path) -> None:
    cmd = [sys.executable, str(KP_DIR / script), *args]
    print(f"  $ {script} {' '.join(args)}")
    r = subprocess.run(cmd, cwd=cwd, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"{script} завершился с кодом {r.returncode}")


def run_pipeline(a: argparse.Namespace) -> int:
    # папка клиента: --client или домен (узнаём после стадии bitrix)
    client_dir = KP_DIR / "clients" / a.client if a.client else None
    if client_dir:
        client_dir.mkdir(parents=True, exist_ok=True)

    # bootstrap: bitrix первой стадией, чтобы получить домен для имени папки
    tmp_dir = client_dir or (KP_DIR / "clients" / f"_deal_{a.deal_id}")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    job_path = tmp_dir / "kp_job.json"
    job = _load(job_path) or {"deal_id": a.deal_id, "stages": {}}

    if a.status:
        print(f"job: {job_path}")
        for s in STAGES:
            st = (job.get("stages") or {}).get(s, {})
            print(f"  {s:<12} {st.get('status', '—'):<8} {st.get('at', '')}")
        return 0

    skip = set()
    if a.skip_metrika:
        skip.add("metrika")
    if a.skip_prodoctorov or not a.prodoctorov:
        skip.add("prodoctorov")

    todo = plan_stages(job, a.force, skip)
    print(f"Сделка {a.deal_id} → {tmp_dir.name} | стадии: {', '.join(todo) or 'всё готово'}")

    def mark(stage, status="done"):
        job.setdefault("stages", {})[stage] = {"status": status, "at": _now()}
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    for stage in todo:
        print(f"▶ {stage}")
        if stage == "bitrix":
            _run("bitrix_audit.py", [str(a.deal_id)], tmp_dir)
        elif stage == "audit":
            bx = _load(tmp_dir / "bitrix.json") or {}
            domain = domain_from_bitrix(bx)
            if not domain:
                raise RuntimeError("домен не определён — проверь bitrix.json или задай --client")
            comps = a.competitors or competitors_from_brief(bx)
            if not comps:
                print("  ⚠ конкуренты не найдены в брифе — бенчмарк будет без соседей "
                      "(можно перезапустить: --force audit --competitors d1 d2)")
            _run("build_kp.py", [domain, *comps], tmp_dir)
        elif stage == "metrika":
            bx = _load(tmp_dir / "bitrix.json") or {}
            try:
                _run("metrika_audit.py", [domain_from_bitrix(bx), str(a.days)], tmp_dir)
            except RuntimeError as e:
                print(f"  ⚠ Метрика недоступна ({e}) — продолжаем без неё")
                mark(stage, "skipped")
                continue
        elif stage == "prodoctorov":
            _run("prodoctorov_audit.py", a.prodoctorov, tmp_dir)
        elif stage == "assemble":
            data = assemble_kp_data(_load(tmp_dir / "bitrix.json"), _load(tmp_dir / "audit.json"),
                                    _load(tmp_dir / "metrika.json"), _load(tmp_dir / "prodoctorov.json"),
                                    brand=a.brand)
            (tmp_dir / "kp_data.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  факты: {len(data['facts'])}, гипотезы: {len(data['hypotheses'])}, "
                  f"ручных шагов: {len(data['manual_checklist'])}")
        elif stage == "scaffold":
            dst = tmp_dir / "kp.html"
            if not dst.exists():
                shutil.copy(pick_template(a.brand) / "kp.html", dst)
                print(f"  эталон скопирован: {dst.relative_to(KP_DIR)}")
            html = dst.read_text(encoding="utf-8")
            bench = (tmp_dir / "seo_benchmark.html")
            probs = (tmp_dir / "problem_solution.html")
            html, missing = inject_auto_blocks(
                html, bench.read_text(encoding="utf-8") if bench.exists() else None,
                probs.read_text(encoding="utf-8") if probs.exists() else None)
            # факты в слайды: плейсхолдеры + баннер просадки трафика
            data = _load(tmp_dir / "kp_data.json") or {}
            for ph, val in deck_substitutions(data, datetime.now().strftime("%d.%m.%Y")).items():
                html = html.replace(ph, val)
            drop_html = render_traffic_drop(data)
            if drop_html and MARK_TRAFFIC in html:
                html = html.replace(MARK_TRAFFIC, drop_html)
            dst.write_text(html, encoding="utf-8")
            if missing:
                print(f"  ⚠ маркеры {missing} в эталоне не найдены — вставь фрагменты вручную "
                      f"(карта слайдов: SEO-KP-PLAYBOOK.md)")
        elif stage == "smeta":
            import kp_smeta
            spec_path = tmp_dir / "smeta.json"
            if spec_path.exists():
                # ручные правки сейлса священны — только пересобираем xlsx
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                print("  smeta.json уже есть — пересобираю xlsx без перезаписи спеки")
            else:
                bx = _load(tmp_dir / "bitrix.json") or {}
                preset_key = preset_for_brief(bx.get("brief_services"))
                spec = {"client": domain_from_bitrix(bx) or tmp_dir.name,
                        "brand": "Acoola Team" if a.brand == "acoola" else "Belberry",
                        "deadline": "", "flags": {"logo_discount": False, "fast_pay": True},
                        **kp_smeta.PRESETS[preset_key]}
                spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
                print(f"  пресет «{preset_key}» (тарифы матрицы) — состав и суммы "
                      f"подтвердить со сметчиком")
            kp_smeta.write_xlsx(spec, tmp_dir / f"Смета_{spec['client']}.xlsx")
        mark(stage)

    print("\nГотово. Дальше руками:")
    print(f"  1. Чек-лист: {tmp_dir / 'kp_data.json'} → manual_checklist")
    print(f"  2. Смета: python3 kp_smeta.py clients/{tmp_dir.name} --init --service seo"
          f" → правка smeta.json → python3 kp_smeta.py clients/{tmp_dir.name}")
    print(f"  3. Цены из сметы → kp.html")
    print(f"  4. bash build.sh clients/{tmp_dir.name} \"КП Belberry — {tmp_dir.name}\"")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("deal_id", type=int)
    p.add_argument("--client")
    p.add_argument("--brand", choices=["belberry", "acoola"], default="belberry",
                   help="шаблон деки: Belberry (медицина) или Acoola Team (остальные ниши)")
    p.add_argument("--competitors", nargs="*", default=[])
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--prodoctorov", nargs="*", default=[])
    p.add_argument("--skip-metrika", action="store_true")
    p.add_argument("--skip-prodoctorov", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--force", help="имя стадии или all")
    return run_pipeline(p.parse_args())


if __name__ == "__main__":
    sys.exit(main())
