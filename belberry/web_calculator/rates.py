"""Single source of truth для ставок и нормативов калькулятора веб-разработки Belberry.

Все цифры в одном месте. Меняешь здесь — пересобираешь Sheet через build_calculator.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HourlyRates:
    base: int = 3100              # ₽/час — типовой разработчик/QA
    design_premium: int = 3500    # ₽/час — авторский дизайн
    tech_lead: int = 4200         # ₽/час — техлид, ревью архитектуры
    project_manager: int = 2800   # ₽/час — координация


@dataclass(frozen=True)
class Platform:
    code: str
    title: str
    license_cost: int             # ₽ единоразово
    hours_discovery: int
    hours_prototype: int
    hours_design_extra: int       # сверх шаблона
    hours_backend: int
    hours_frontend: int
    hours_qa: int
    hours_launch: int
    note: str = ""


PLATFORMS: dict[str, Platform] = {
    "strapi": Platform(
        code="strapi", title="Strapi (шаблон Belberry)",
        license_cost=125_000,
        hours_discovery=8, hours_prototype=12, hours_design_extra=10,
        hours_backend=25, hours_frontend=15, hours_qa=30, hours_launch=8,
        note="Готовый шаблон Belberry. Быстро. Для типовых клиник/корп.сайтов.",
    ),
    "bitrix": Platform(
        code="bitrix", title="1С-Битрикс (шаблон Belberry)",
        license_cost=84_000,           # «Малый бизнес»
        hours_discovery=8, hours_prototype=16, hours_design_extra=10,
        hours_backend=30, hours_frontend=20, hours_qa=30, hours_launch=8,
        note="Сложные каталоги, 1С-интеграция, бизнес-процессы.",
    ),
    "tilda": Platform(
        code="tilda", title="Tilda Pro",
        license_cost=9_000,            # годовая подписка
        hours_discovery=6, hours_prototype=8, hours_design_extra=12,
        hours_backend=4, hours_frontend=8, hours_qa=16, hours_launch=4,
        note="Лендинги, простые корп.сайты. Минимум кастома.",
    ),
    "wordpress": Platform(
        code="wordpress", title="WordPress + WooCommerce",
        license_cost=0,
        hours_discovery=6, hours_prototype=10, hours_design_extra=14,
        hours_backend=20, hours_frontend=16, hours_qa=20, hours_launch=6,
        note="Корп.сайты, блоги, простой e-com. Дешевле Битрикса, но менее гибко.",
    ),
    "custom": Platform(
        code="custom", title="Индивидуальная разработка (Next.js + Headless CMS)",
        license_cost=0,
        hours_discovery=16, hours_prototype=30, hours_design_extra=80,
        hours_backend=80, hours_frontend=60, hours_qa=50, hours_launch=16,
        note="Авторский дизайн, премиум, любая логика. Дольше и дороже.",
    ),
}


@dataclass(frozen=True)
class PageType:
    code: str
    title: str
    hours_per_unit: float
    default_count: int


PAGE_TYPES: list[PageType] = [
    PageType("home", "Главная", 8, 1),
    PageType("about", "О компании", 4, 1),
    PageType("service_standard", "Услуга (типовая)", 3, 5),
    PageType("service_premium", "Услуга (премиум дизайн)", 8, 0),
    PageType("doctor", "Карточка врача/специалиста", 1.5, 0),
    PageType("blog_post", "Статья блога (шаблонная)", 1, 10),
    PageType("product_card", "Карточка товара (шаблонная)", 0.5, 0),
    PageType("case", "Кейс / проект", 2.5, 0),
    PageType("review", "Отзывы (блок)", 0.5, 1),
    PageType("faq", "FAQ (блок)", 0.5, 1),
    PageType("contacts", "Контакты", 2, 1),
    PageType("legal", "Юридические (Доставка/Оплата/Политика)", 1.5, 3),
]


@dataclass(frozen=True)
class Integration:
    code: str
    title: str
    hours: int
    note: str = ""
    default: bool = False


INTEGRATIONS: list[Integration] = [
    Integration("crm",       "CRM (Bitrix24 / AmoCRM)",                  8, "Передача заявок в CRM клиента", default=True),
    Integration("recaptcha", "ReCaptcha + honeypot",                    4, "Защита форм. Рекомендуется всегда.", default=True),
    Integration("seo_base",  "Базовые SEO (meta, sitemap, robots)",     6, "Технический минимум.", default=True),
    Integration("analytics", "Яндекс.Метрика + GA4 + цели",             4, "Базовый замер.",        default=True),
    Integration("calltouch", "Сквозная аналитика (Roistat/Calltouch)",  6, "По запросу клиента."),
    Integration("yclients",  "Онлайн-расписание (YClients / МИС)",     12, "Медицина."),
    Integration("acquiring", "Эквайринг карт",                         16, "E-com / онлайн-оплата."),
    Integration("chat",      "Чат (JivoSite / Telegram-чат)",           4, "Лидогенерация."),
    Integration("onec",      "Интеграция с 1С (каталог/остатки)",      32, "E-com."),
    Integration("tg_bot",    "Telegram-бот для заявок",                 8, "Канал заявок."),
    Integration("import",    "Импорт/экспорт каталога (CSV/XML)",      20, "E-com."),
    Integration("multilang", "Мультиязычность (за каждый доп. язык)",  16, "Кратно числу языков."),
    Integration("email_tmpl","Шаблоны транзакционных писем",            6, "Уведомления, восстановление пароля."),
    Integration("dns_mail",  "Настройка доменной почты",                3, ""),
]


@dataclass(frozen=True)
class SeoLevel:
    code: str
    title: str
    hours: int
    note: str


SEO_LEVELS: list[SeoLevel] = [
    SeoLevel("none",     "Не нужно",                                0, "Клиент сам или другой подрядчик"),
    SeoLevel("base",     "Базовый (meta, sitemap, schema)",         6, "Технический минимум, входит в дефолт"),
    SeoLevel("extended", "Расширенный (структура + сем.ядро ≤200)", 40, "Семантика, кластеризация, ТЗ копирайтеру"),
    SeoLevel("full",     "Полный (сем.ядро + on-page для ВСЕХ стр)",120,"Под пакет на продвижение"),
]


@dataclass(frozen=True)
class ContentRates:
    text_service: int = 5_200      # текст страницы услуги (с медкопирайтером)
    text_product: int = 2_600      # текст карточки товара
    text_blog: int = 7_000         # статья блога 3000+ знаков
    text_brief: int = 1_300        # ТЗ на текст (SEO-структура)
    text_landing_block: int = 3_500  # блок текста для лендинга


@dataclass(frozen=True)
class Discounts:
    copyright_inhouse: float = 0.10   # «копирайт — наш»
    speed_signing: float = 0.05       # договор подписан в 14 дней с КП
    vat: float = 0.05                 # НДС 5% при УСН


@dataclass(frozen=True)
class BudgetRules:
    over_budget_threshold: float = 0.20   # допустимое превышение 20%
    quote_validity_days: int = 14         # срок действия КП
    expected_send_business_days: int = 3  # КП должно уйти клиенту за N раб.дн.


@dataclass(frozen=True)
class Buffer:
    revisions_pct: float = 0.15           # запас на правки после демо
    risk_pct_default: float = 0.10        # дефолтный риск-буфер


@dataclass(frozen=True)
class Rates:
    hourly: HourlyRates = field(default_factory=HourlyRates)
    content: ContentRates = field(default_factory=ContentRates)
    discounts: Discounts = field(default_factory=Discounts)
    budget: BudgetRules = field(default_factory=BudgetRules)
    buffer: Buffer = field(default_factory=Buffer)


RATES = Rates()

PROJECT_TYPES = [
    ("clinic",    "Клиника / медцентр"),
    ("corporate", "Корпоративный сайт"),
    ("landing",   "Лендинг / промо-страница"),
    ("ecom",      "E-commerce / интернет-магазин"),
    ("portal",    "Портал / многосайтовая система"),
    ("services",  "Сайт услуг (b2b/b2c, без e-com)"),
]

MANAGERS = [
    "Деговцова Е.",
    "Семенихин Е.",
    "Гордиенко Е.",
    "Иной (заполнить вручную)",
]

LEAD_SOURCES = [
    "Реклама контекст",
    "Реклама таргет",
    "SEO",
    "Рекомендация",
    "Холодный обзвон",
    "Входящий звонок/форма",
    "Конференция/выставка",
    "Партнёр",
    "Иное",
]

SPHERES = [
    "Медицина",
    "E-com",
    "B2B-услуги",
    "B2C-услуги",
    "Корпоративный",
    "Образование",
    "Иное",
]
