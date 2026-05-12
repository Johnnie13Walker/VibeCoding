"""Стадия enrich-web — обогащение строк status=NEW.

Источники (в порядке убывания доверия):
  1. uf            — UF_INN-кандидат, найденный discover-стадией
  2. web           — GET https://{web}/ + /requisites/ + /реквизиты/ + /about/ + /policy/
  3. title         — если TITLE компании выглядит как домен — пробуем как web
  4. rusprofile    — fallback по поисковой выдаче rusprofile.ru

Безопасность:
- in_active_deal_merge=True → пропускаем (компания занята deal-merge).
- HttpFetcher — pluggable, в тестах подменяется monkeypatch'ем.
- Rate-limit: sleep(ENRICH_HTTP_DELAY_S) между HTTP-вызовами.
"""
from __future__ import annotations

import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Optional, Union
from zoneinfo import ZoneInfo

from ..config import (
    ENRICH_HTTP_DELAY_S,
    ENRICH_HTTP_RETRIES,
    ENRICH_HTTP_TIMEOUT_S,
    ENRICH_USER_AGENT,
)
from ..domain import normalize_domain
from ..models import QueueRow, is_valid_inn_format, normalize_inn
from ..sheet_store import read_queue, replace_row, update_row
from ..sheets_client import SheetsClient
from ..state import Status, is_at_least

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

WEB_PATHS = ("/", "/requisites/", "/реквизиты/", "/about/", "/policy/", "/о-клинике/", "/contacts/", "/контакты/")

# Bitrix-плейсхолдеры и явный мусор в TITLE — не пытаемся использовать как домен.
TITLE_BLACKLIST = re.compile(
    r"(битрикс24\s+помогает|placeholder|новая\s+компания|без\s+названия|^id\s*\d+$)",
    re.IGNORECASE,
)

# Whitelist TLD для жёсткой пост-валидации normalize_domain.
_DOMAIN_TLD_WHITELIST = frozenset({
    "ru", "рф", "com", "su", "org", "net", "info", "by", "kz", "ua",
    "ee", "lv", "lt", "kg", "am", "ge", "az", "uz", "tj", "md",
    "gov", "edu", "biz", "store", "shop", "online", "ai",
})

# Stoplist ИНН — известный мусор / явные fake-значения.
INN_STOPLIST = frozenset({
    "0000000000", "0123456789", "1234567890",
    "111111111100", "999999999999", "123456789012",
    "173937695939",  # fake ИНН из инцидента enrich-web --limit 30
})

# Двухступенчатый ИНН-парсинг: сначала только рядом с label.
INN_NEAR_LABEL = re.compile(
    r"(?:ИНН|INN|Tax\s*ID)[\s:№#]*?(\d{10}(?:\d{2})?)\b",
    re.IGNORECASE,
)
INN_BARE = re.compile(r"\b(\d{10}(?:\d{2})?)\b")


def _is_safe_domain_candidate(domain: str | None) -> bool:
    """Постфильтр для normalize_domain: отвергаем мусор, не похожий на реальный хост."""
    if not domain:
        return False
    s = domain.strip()
    if not s or " " in s or len(s) > 64:
        return False
    parts = s.rsplit(".", 1)
    if len(parts) != 2:
        return False
    tld = parts[1].lower()
    if tld in _DOMAIN_TLD_WHITELIST:
        return True
    # допускаем неперечисленные 2-3-буквенные ASCII TLD (futureproof)
    if 2 <= len(tld) <= 3 and tld.isascii() and tld.isalpha():
        return True
    return False


def _is_junk_inn(value: str) -> bool:
    """Отсев очевидно-фейковых ИНН (stoplist + строго одинаковые цифры)."""
    if not value:
        return True
    if value in INN_STOPLIST:
        return True
    if len(set(value)) == 1:  # 1111111111, 9999999999, 000000000000
        return True
    return False


# ----- HttpFetcher abstraction -----

# Disable InsecureRequestWarning — SSL fallback ниже намеренно ходит без
# verify=True для сайтов с expired/self-signed сертификатами (часто у клиник).
try:  # pragma: no cover — best-effort
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    ssl_unsafe: bool = False  # True если получен через verify=False fallback


# Базовые backoff'ы для retry-цикла. DNS-ошибки получают расширенную серию —
# overloaded local resolver часто отдаёт ответ после большей паузы.
_BASE_BACKOFF = (1.0, 2.0, 3.0)
_DNS_BACKOFF = (2.0, 5.0, 10.0)
_DNS_EXTRA_ATTEMPTS = 2  # сверх ENRICH_HTTP_RETRIES, только если детектирован DNS-fail


def _is_dns_error(exc: BaseException | None) -> bool:
    """Грубо детектируем NameResolutionError по тексту ошибки.

    requests заворачивает urllib3.NameResolutionError в ConnectionError;
    структурного API нет, поэтому substring-match самый надёжный путь.
    """
    if exc is None:
        return False
    msg = str(exc)
    return (
        "NameResolution" in msg
        or "Name or service not known" in msg
        or "nodename nor servname" in msg
    )


def _classify_error(exc: BaseException | None) -> str:
    """Короткий ярлык типа ошибки для финального лога (ssl/dns/conn/timeout/...)."""
    if exc is None:
        return "unknown"
    import requests  # local — не тянем requests на module-import
    if isinstance(exc, requests.exceptions.SSLError):
        return "ssl"
    if _is_dns_error(exc):
        return "dns"
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "conn"
    return type(exc).__name__.lower()


class HttpFetcher:
    """Production fetcher через requests (lazy import — в тестах подменяется).

    SSL fallback: при requests.exceptions.SSLError повторяем тот же URL с
    verify=False (локально для запроса, не глобально). FetchResult помечается
    ssl_unsafe=True чтобы вышестоящие слои знали.
    """

    def __init__(self, timeout: float = ENRICH_HTTP_TIMEOUT_S, retries: int = ENRICH_HTTP_RETRIES):
        self.timeout = timeout
        self.retries = retries
        self._session = None

    def _ensure_session(self):  # pragma: no cover — реальный HTTP не вызывается в тестах
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({"User-Agent": ENRICH_USER_AGENT})
        return self._session

    def _do_get(self, url: str, *, verify: bool) -> FetchResult:
        """Один HTTP GET. Бросает исключение — retry делает fetch()."""
        session = self._ensure_session()
        r = session.get(url, timeout=self.timeout, allow_redirects=True, verify=verify)
        return FetchResult(url=r.url, status=r.status_code, text=r.text or "")

    def fetch(self, url: str) -> FetchResult | None:
        import requests

        last_err: BaseException | None = None
        attempt = 0
        dns_extra_used = 0
        max_attempts = self.retries  # может вырасти, если поймали DNS-fail

        while attempt < max_attempts:
            try:
                return self._do_get(url, verify=True)
            except requests.exceptions.SSLError as ssl_exc:
                # SSL fallback — пробуем тот же URL без verify (expired/self-signed)
                last_err = ssl_exc
                try:
                    result = self._do_get(url, verify=False)
                    result.ssl_unsafe = True
                    return result
                except Exception as inner:
                    last_err = inner
            except Exception as exc:
                last_err = exc

            # Подбираем backoff: DNS получает расширенную серию + дополнительные attempts.
            if _is_dns_error(last_err):
                idx = min(attempt, len(_DNS_BACKOFF) - 1)
                backoff = _DNS_BACKOFF[idx]
                if (
                    dns_extra_used < _DNS_EXTRA_ATTEMPTS
                    and max_attempts < self.retries + _DNS_EXTRA_ATTEMPTS
                ):
                    max_attempts += 1
                    dns_extra_used += 1
            else:
                idx = min(attempt, len(_BASE_BACKOFF) - 1)
                backoff = _BASE_BACKOFF[idx]

            time.sleep(backoff)
            attempt += 1

        # Один verdict-лог на URL — иначе на 8 paths × 5 attempts получаем 40 строк.
        print(f"[fetch] {url}: {attempt} attempts failed (last: {_classify_error(last_err)})")
        return None


# Inline alias for tests: same signature as HttpFetcher.fetch
FetcherFn = Callable[[str], Optional[FetchResult]]


# ----- Stage -----

def run(
    sheets: SheetsClient,
    *,
    fetcher: Union[HttpFetcher, FetcherFn, None] = None,
    limit: int | None = None,
    sleep_s: float = ENRICH_HTTP_DELAY_S,
) -> dict:
    fetch = _resolve_fetcher(fetcher)
    now = datetime.now(MOSCOW_TZ)

    queue = read_queue(sheets)
    targets: list[tuple[int, QueueRow]] = []
    skipped_active = 0
    for row_number, row in queue:
        if row.status != Status.NEW:
            continue
        if row.in_active_deal_merge:
            skipped_active += 1
            continue
        targets.append((row_number, row))
        if limit is not None and len(targets) >= limit:
            break

    print(f"[enrich-web] таргетов: {len(targets)}; пропущено активных deal-merge: {skipped_active}")

    enriched = 0
    failed = 0
    by_source: dict[str, int] = {}

    manual_review = 0
    for idx, (row_number, row) in enumerate(targets):
        if idx > 0:
            time.sleep(sleep_s)
        inn, source, name = _enrich_one(row, fetch, sleep_s=sleep_s)
        if inn:
            # «rusprofile_unverified» — слабый сигнал, без geo-подтверждения; уходит в MANUAL_REVIEW.
            target_status = (
                Status.MANUAL_REVIEW
                if source == "rusprofile_unverified"
                else Status.ENRICHED
            )
            err_msg = (
                "rusprofile match без geo-подтверждения — нужна ручная проверка"
                if target_status == Status.MANUAL_REVIEW
                else None
            )
            updated = replace_row(
                row,
                discovered_inn=inn,
                discovered_name=name,
                discovered_source=source,
                status=target_status,
                last_action_at=now,
                error_message=err_msg,
            )
            if target_status == Status.MANUAL_REVIEW:
                manual_review += 1
            else:
                enriched += 1
            by_source[source] = by_source.get(source, 0) + 1
        else:
            updated = replace_row(
                row,
                status=Status.ENRICH_FAILED,
                last_action_at=now,
                error_message="enrich-web: no INN found",
            )
            failed += 1
        update_row(sheets, row_number, updated)

    print(
        f"[enrich-web] ENRICHED: {enriched}; MANUAL_REVIEW: {manual_review}; "
        f"FAILED: {failed}; by_source: {by_source}"
    )
    return {
        "enriched": enriched,
        "manual_review": manual_review,
        "failed": failed,
        "skipped_in_active_merge": skipped_active,
        "by_source": by_source,
        "ts_msk": now.isoformat(timespec="seconds"),
    }


def _resolve_fetcher(fetcher: HttpFetcher | FetcherFn | None) -> FetcherFn:
    if fetcher is None:
        return HttpFetcher().fetch
    if hasattr(fetcher, "fetch"):
        return fetcher.fetch  # type: ignore[union-attr]
    return fetcher  # callable


def _enrich_one(
    row: QueueRow,
    fetch: FetcherFn,
    *,
    sleep_s: float,
) -> tuple[str | None, str | None, str | None]:
    """Возвращает (inn, source, name) или (None, None, None)."""

    # Source 1 — UF
    if row.uf_inn_candidate:
        normalized = normalize_inn(row.uf_inn_candidate)
        if normalized:
            return normalized, "uf", row.company_name or None

    # Source 2 — WEB / domain из deal-merge
    web_target = row.web or row.domain
    if web_target:
        inn, name = _try_web(web_target, fetch, sleep_s=sleep_s)
        if inn:
            return inn, "web", name or row.company_name

    # Source 3 — TITLE as domain
    # Отрезаем дефолтные плейсхолдеры Bitrix и мусор: "Битрикс24 помогает...",
    # "Новая компания", "ID 12345" и т.п. — попытка resolve-нуть такое
    # как домен приводит к фолсам и фейковым ИНН.
    if row.company_name and not TITLE_BLACKLIST.search(row.company_name):
        title_domain = normalize_domain(row.company_name)
        if _is_safe_domain_candidate(title_domain):
            inn, name = _try_web(title_domain, fetch, sleep_s=sleep_s)
            if inn:
                return inn, "title", name or row.company_name

    # Source 4 — rusprofile fallback (с geo-верификацией)
    if row.company_name:
        inn, name, geo_tokens = _try_rusprofile(row.company_name, fetch)
        if inn:
            verified = _verify_rusprofile_match(
                geo_tokens=geo_tokens,
                bitrix_title=row.company_name,
                web=web_target,
            )
            source = "rusprofile_verified" if verified else "rusprofile_unverified"
            return inn, source, name

    return None, None, None


def _try_web(web_or_domain: str, fetch: FetcherFn, *, sleep_s: float) -> tuple[str | None, str | None]:
    """Обходим набор стандартных путей сайта и ищем ИНН в тексте."""
    base_url = _normalize_base_url(web_or_domain)
    if not base_url:
        return None, None
    for path_idx, path in enumerate(WEB_PATHS):
        url = base_url.rstrip("/") + path
        if path_idx > 0:
            time.sleep(sleep_s)
        result = fetch(url)
        if not result:
            # Если даже корень домена не ответил после retry fetcher'а, остальные
            # стандартные paths почти наверняка дадут тот же DNS/timeout.
            if path_idx == 0:
                return None, None
            continue
        if result.status >= 400:
            continue
        inn = extract_inn_from_text(result.text, source_url=result.url or url)
        if inn:
            name = extract_company_name_from_html(result.text)
            return inn, name
    return None, None


def _try_rusprofile(
    company_name: str,
    fetch: FetcherFn,
) -> tuple[str | None, str | None, list[str]]:
    """Возвращает (inn, name, geo_tokens) или (None, None, []).

    geo_tokens — список низкокейс-токенов адреса/региона из rusprofile-карточки
    (используется верификатором). Может быть пустым, если карточка не отдала адрес.
    """
    query = urllib.parse.quote_plus(company_name)
    result = fetch(f"https://www.rusprofile.ru/search?query={query}")
    if not result or result.status >= 400:
        return None, None, []
    # rusprofile в выдаче выводит ИНН отдельной строкой `ИНН: 7707083893`
    inn = extract_inn_from_text(result.text, source_url=result.url)
    if not inn:
        return None, None, []
    name = extract_company_name_from_html(result.text) or company_name
    geo_tokens = extract_rusprofile_geo_tokens(result.text)
    return inn, name, geo_tokens


def _normalize_base_url(web_or_domain: str) -> str | None:
    s = (web_or_domain or "").strip()
    if not s:
        return None
    if s.startswith(("http://", "https://")):
        return s
    return f"https://{s}"


# ----- text parsing -----

NAME_TAG = re.compile(r"<title[^>]*>([^<]{3,200})</title>", re.IGNORECASE)


def extract_inn_from_text(text: str, *, source_url: str | None = None) -> str | None:
    """Достать первый валидный ИНН из произвольного текста (HTML/markdown).

    Стратегия:
      1. Сначала ищем рядом со словом-меткой ИНН/INN/Tax ID (сильный сигнал).
      2. Bare 10/12-значное число — fallback ТОЛЬКО на страницах реквизитов
         (URL содержит `requisites` / `реквизиты`), плюс отсев stoplist/junk.

    Без сильного контекста (label или requisites-URL) bare-числа отбрасываются:
    они ловят timestamps, ID, телефоны без префикса и т.п.
    """
    if not text:
        return None

    # 1. labeled — наиболее надёжно.
    for m in INN_NEAR_LABEL.finditer(text):
        candidate = normalize_inn(m.group(1))
        if candidate and not _is_junk_inn(candidate):
            return candidate

    # 2. bare-fallback разрешён только на страницах реквизитов.
    if source_url:
        lowered = source_url.lower()
        if "requisites" in lowered or "реквизиты" in lowered or "%d1%80%d0%b5%d0%ba%d0%b2" in lowered:
            for m in INN_BARE.finditer(text):
                raw = m.group(1)
                start = m.start(1)
                window = text[max(0, start - 6):start]
                # пропускаем «телефонную» пунктуацию рядом
                if any(ch in window for ch in "+()-"):
                    continue
                candidate = normalize_inn(raw)
                if not candidate or not is_valid_inn_format(candidate):
                    continue
                if _is_junk_inn(candidate):
                    continue
                return candidate

    return None


def extract_company_name_from_html(text: str) -> str | None:
    if not text:
        return None
    m = NAME_TAG.search(text)
    if not m:
        return None
    return m.group(1).strip()[:200] or None


# ----- rusprofile geo verification -----

# Адрес/регион на rusprofile-карточке обычно лежит в блоках с class содержащим
# "company-address" или label "Адрес:". Парсим достаточно широко.
_RUSPROFILE_ADDRESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"<[^>]*class=\"[^\"]*(?:company-address|address)[^\"]*\"[^>]*>([^<]{3,300})</",
        re.IGNORECASE,
    ),
    re.compile(r"Адрес[^:]*:\s*([^<\n]{3,300})", re.IGNORECASE),
    re.compile(r"Регион[^:]*:\s*([^<\n]{3,200})", re.IGNORECASE),
    re.compile(r"<address[^>]*>([^<]{3,300})</address>", re.IGNORECASE),
)

# Мини-словарь TLD → русские geo-токены для проверки .ru-доменов с региональной семантикой.
_TLD_HINTS: dict[str, tuple[str, ...]] = {
    "msk": ("москва", "moscow", "московская"),
    "spb": ("санкт-петербург", "петербург", "ленинградская"),
    "krd": ("краснодар",),
    "ekb": ("екатеринбург", "свердловская"),
    "nsk": ("новосибирск",),
    "kzn": ("казань", "татарстан"),
    "nn": ("нижний новгород", "новгород"),
}


def extract_rusprofile_geo_tokens(text: str) -> list[str]:
    """Достать low-case geo-токены из адресных блоков rusprofile.

    Делим адрес по запятым / точкам / переносам и возвращаем токены длиннее 3
    символов. Не делаем NER — простой substring-match на следующем шаге.
    """
    if not text:
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    for pat in _RUSPROFILE_ADDRESS_PATTERNS:
        for m in pat.finditer(text):
            blob = m.group(1).strip().lower()
            blob = re.sub(r"&[a-z#0-9]+;", " ", blob)  # entities → space
            for part in re.split(r"[,;/\.\n\t]+", blob):
                part = part.strip(" -–—«»\"'()[]<>:;")
                # Дополнительно бьём по словам — длинные «г. Краснодар» → «г», «краснодар».
                for word in re.split(r"\s+", part):
                    word = word.strip(" -–—«»\"'()[]<>:;.")
                    if len(word) < 4:
                        continue
                    if word in seen:
                        continue
                    # Отсев чисто-цифровых и почтовых индексов.
                    if word.isdigit():
                        continue
                    seen.add(word)
                    tokens.append(word)
    return tokens


def _domain_geo_hints(web: str | None) -> list[str]:
    """Если web вида msk-clinic.ru / spb-foo.ru — вернуть geo-токены из _TLD_HINTS."""
    if not web:
        return []
    s = web.lower()
    out: list[str] = []
    for hint, geo_words in _TLD_HINTS.items():
        # `msk-`, `-msk.`, `.msk.` — лёгкие маркеры
        if re.search(rf"(?:^|[\W_]){re.escape(hint)}(?:[\W_]|$)", s):
            out.extend(geo_words)
    return out


def _verify_rusprofile_match(
    *,
    geo_tokens: list[str],
    bitrix_title: str | None,
    web: str | None,
) -> bool:
    """Проверка совпадения geo-токенов rusprofile-карточки с upstream-сигналами row.

    Match → возвращаем True (используем source="rusprofile_verified", статус ENRICHED).
    No match → False (source="rusprofile_unverified", статус MANUAL_REVIEW).

    Логика:
      1. Если geo_tokens пуст → не верифицировано (consrvative: пользователь сам решит).
      2. Любое substring-совпадение токена с bitrix_title.lower() → match.
      3. Любое совпадение токена с web.lower() (например .krd. поддомен) → match.
      4. Domain-hints: msk-* → москва и т.п. — если в geo_tokens есть москва → match.
    """
    if not geo_tokens:
        return False
    bt = (bitrix_title or "").lower()
    web_l = (web or "").lower()
    for token in geo_tokens:
        if token and bt and token in bt:
            return True
        if token and web_l and token in web_l:
            return True
    # Heuristic поддомены через TLD_HINTS
    hints = _domain_geo_hints(web)
    if hints:
        for hint in hints:
            if any(hint in token or token in hint for token in geo_tokens):
                return True
    return False


# ----- public helpers exposed for tests -----

def iter_candidate_urls(domain_or_url: str) -> Iterable[str]:
    """Те же URL, что обходит _try_web — для тестов и debug."""
    base = _normalize_base_url(domain_or_url)
    if not base:
        return []
    return [base.rstrip("/") + p for p in WEB_PATHS]
