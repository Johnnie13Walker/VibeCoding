"""Сборка тем для постов по дневной/периодной работе."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
from typing import Mapping
from zoneinfo import ZoneInfo

from ..config import DEFAULT_CONFIG
from ..providers.tasks_provider import TasksProvider
from ..schemas.content import ContentPostDraft, ContentTheme, ContentTopicsDigest
from ..schemas.task import TaskDaySnapshot


@dataclass(frozen=True)
class ContentTopicsWorkflowDeps:
    engineer_root: Path
    architect_root: Path
    tasks_provider: TasksProvider | None = None
    git_binary: str = "git"
    gh_binary: str = "gh"
    max_commits: int = 80

    @classmethod
    def from_env(cls, env_data: Mapping[str, str] | None = None) -> "ContentTopicsWorkflowDeps":
        env_payload = dict(env_data or {})
        engineer_root = Path(
            env_payload.get("CLOUDBOT_ENGINEER_ROOT")
            or Path(__file__).resolve().parents[3]
        )
        architect_root = Path(
            env_payload.get("CLOUDBOT_ARCHITECT_ROOT")
            or _derive_architect_root(engineer_root)
        )
        return cls(
            engineer_root=engineer_root,
            architect_root=architect_root,
        )


@dataclass(frozen=True)
class GitActivity:
    subjects: tuple[str, ...]
    files: tuple[str, ...]
    commit_count: int


@dataclass(frozen=True)
class StatusActivity:
    highlights: tuple[str, ...]
    entry_count: int


@dataclass(frozen=True)
class TasksActivity:
    highlights: tuple[str, ...]
    task_count: int


@dataclass(frozen=True)
class PullRequestActivity:
    highlights: tuple[str, ...]
    pr_count: int


def _derive_architect_root(engineer_root: Path) -> Path:
    if len(engineer_root.parents) >= 3:
        return engineer_root.parents[2] / "architect"
    return engineer_root.parent / "architect"


def run_content_topics_workflow(
    *,
    date_msk: str,
    period_key: str,
    deps: ContentTopicsWorkflowDeps,
) -> dict[str, object]:
    anchor = datetime.strptime(date_msk, "%d.%m.%Y").replace(tzinfo=ZoneInfo(DEFAULT_CONFIG.timezone))
    period = _resolve_period(anchor, period_key)
    limitations: list[str] = []

    git_activity = _collect_git_activity(period["since"], period["until"], deps)
    if git_activity is None:
        git_activity = GitActivity(subjects=tuple(), files=tuple(), commit_count=0)
        limitations.append("Git-история за период недоступна.")

    status_activity = _collect_status_activity(period["since"], period["until"], deps)
    if status_activity is None:
        status_activity = StatusActivity(highlights=tuple(), entry_count=0)
        limitations.append("docs/STATUS.md не дал фактуру за период.")

    tasks_activity = _collect_tasks_activity(date_msk, period_key, deps)
    if tasks_activity is None:
        tasks_activity = TasksActivity(highlights=tuple(), task_count=0)
        limitations.append("Источник задач не дал дополнительной фактуры.")

    pr_activity = _collect_pr_activity(period["since"], deps)
    if pr_activity is None:
        pr_activity = PullRequestActivity(highlights=tuple(), pr_count=0)
        limitations.append("PR-источник недоступен или не настроен.")

    digest = build_content_topics_digest(
        date_msk=date_msk,
        period_key=period_key,
        period_label=str(period["label"]),
        git_activity=git_activity,
        status_activity=status_activity,
        tasks_activity=tasks_activity,
        pr_activity=pr_activity,
        limitations=tuple(limitations),
    )
    return {
        "text": "",
        "digest": digest,
        "should_send": bool(digest.themes),
        "skip_reason": "content_topics_no_material" if not digest.themes else "",
    }


def run_content_post_workflow(
    *,
    date_msk: str,
    period_key: str,
    topic_index: int,
    tone: str,
    deps: ContentTopicsWorkflowDeps,
) -> dict[str, object]:
    result = run_content_topics_workflow(
        date_msk=date_msk,
        period_key=period_key,
        deps=deps,
    )
    digest = result["digest"]
    themes = digest.themes
    if topic_index < 1 or topic_index > len(themes):
        return {
            "draft": None,
            "topic_index": topic_index,
            "text": f"Тема {topic_index} недоступна. Сначала запроси /topics и выбери номер из списка.",
            "should_send": True,
        }

    theme = themes[topic_index - 1]
    draft = build_content_post_draft(theme, tone=tone)
    return {
        "draft": draft,
        "topic_index": topic_index,
        "text": "",
        "should_send": True,
    }


def build_content_topics_digest(
    *,
    date_msk: str,
    period_key: str,
    period_label: str,
    git_activity: GitActivity,
    status_activity: StatusActivity,
    tasks_activity: TasksActivity,
    pr_activity: PullRequestActivity,
    limitations: tuple[str, ...] = tuple(),
) -> ContentTopicsDigest:
    area_counts = _classify_activity(git_activity.files)
    themes = _build_themes(area_counts, git_activity, status_activity, tasks_activity, pr_activity)
    summary = _build_summary(period_label, git_activity, status_activity, tasks_activity, pr_activity, themes)

    return ContentTopicsDigest(
        date_msk=date_msk,
        period_key=period_key,
        period_label=period_label,
        summary=summary,
        themes=themes,
        limitations=limitations,
        commit_count=git_activity.commit_count,
        status_entry_count=status_activity.entry_count,
    )


def build_content_post_draft(theme: ContentTheme, *, tone: str = "default") -> ContentPostDraft:
    normalized_tone = _normalize_tone(tone)
    hook = _build_belberry_hook(theme, tone=normalized_tone)
    outline = _build_outline(normalized_tone)
    evidence_block = ""
    if theme.evidence:
        evidence_block = "\n".join(f"- {item}" for item in theme.evidence[:3])
    post_text = _build_post_text(theme, hook=hook, tone=normalized_tone, evidence_block=evidence_block)
    return ContentPostDraft(
        theme=theme,
        tone=normalized_tone,
        hook=hook,
        outline=outline,
        post_text=post_text,
    )


def _resolve_period(anchor: datetime, period_key: str) -> dict[str, object]:
    start_of_day = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    normalized = str(period_key or "day").strip().lower()
    if normalized == "week":
        since = start_of_day - timedelta(days=6)
        until = start_of_day + timedelta(days=1)
        return {
            "since": since,
            "until": until,
            "label": f"за 7 дней до {anchor.strftime('%d.%m.%Y')}",
        }
    if normalized == "all":
        return {
            "since": None,
            "until": None,
            "label": "за весь доступный период",
        }
    return {
        "since": start_of_day,
        "until": start_of_day + timedelta(days=1),
        "label": f"за {anchor.strftime('%d.%m.%Y')}",
    }


def _collect_git_activity(
    since: datetime | None,
    until: datetime | None,
    deps: ContentTopicsWorkflowDeps,
) -> GitActivity | None:
    args = [
        deps.git_binary,
        "log",
        f"-n{deps.max_commits}",
        "--date=iso-strict",
        "--pretty=format:__COMMIT__%n%H%x1f%s%x1f%ad",
        "--name-only",
    ]
    if since is not None:
        args.append(f"--since={since.isoformat()}")
    if until is not None:
        args.append(f"--until={until.isoformat()}")

    result = subprocess.run(
        args,
        cwd=deps.engineer_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    subjects: list[str] = []
    files: list[str] = []
    commit_count = 0
    current_commit_open = False
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "__COMMIT__":
            commit_count += 1
            current_commit_open = True
            continue
        if current_commit_open:
            parts = line.split("\x1f")
            if len(parts) >= 3:
                subjects.append(parts[1].strip())
            current_commit_open = False
            continue
        files.append(line)

    return GitActivity(
        subjects=tuple(subjects[:12]),
        files=tuple(files),
        commit_count=commit_count,
    )


def _collect_status_activity(
    since: datetime | None,
    until: datetime | None,
    deps: ContentTopicsWorkflowDeps,
) -> StatusActivity | None:
    status_path = deps.architect_root / "docs" / "STATUS.md"
    if not status_path.exists():
        return None

    content = status_path.read_text(encoding="utf-8")
    highlights: list[str] = []
    entry_count = 0
    current_date: datetime | None = None
    current_highlight = ""

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("- Дата и время:"):
            if _status_entry_in_range(current_date, since, until) and current_highlight:
                entry_count += 1
                highlights.append(current_highlight)
            current_highlight = ""
            current_date = _parse_status_datetime(line.removeprefix("- Дата и время:").strip())
            continue
        if line.startswith("- Что сделано:"):
            current_highlight = line.removeprefix("- Что сделано:").strip()

    if _status_entry_in_range(current_date, since, until) and current_highlight:
        entry_count += 1
        highlights.append(current_highlight)

    return StatusActivity(
        highlights=tuple(highlights[:5]),
        entry_count=entry_count,
    )


def _collect_tasks_activity(
    date_msk: str,
    period_key: str,
    deps: ContentTopicsWorkflowDeps,
) -> TasksActivity | None:
    if deps.tasks_provider is None:
        return None

    snapshots: list[TaskDaySnapshot] = []
    if period_key == "week":
        anchor = datetime.strptime(date_msk, "%d.%m.%Y")
        for offset in range(0, 7):
            current = (anchor - timedelta(days=offset)).strftime("%d.%m.%Y")
            try:
                snapshots.append(deps.tasks_provider.get_day_snapshot(current))
            except Exception:  # noqa: BLE001
                continue
    else:
        try:
            snapshots.append(deps.tasks_provider.get_day_snapshot(date_msk))
        except Exception:  # noqa: BLE001
            return None

    highlights: list[str] = []
    task_count = 0
    seen_titles: set[str] = set()
    for snapshot in snapshots:
        if not snapshot.source_available:
            continue
        for task in (*snapshot.tasks_for_today, *snapshot.overdue_tasks):
            normalized = task.title.strip()
            if not normalized:
                continue
            task_count += 1
            key = normalized.lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            highlights.append(normalized)
            if len(highlights) >= 4:
                break
        if len(highlights) >= 4:
            break

    return TasksActivity(highlights=tuple(highlights), task_count=task_count)


def _collect_pr_activity(
    since: datetime | None,
    deps: ContentTopicsWorkflowDeps,
) -> PullRequestActivity | None:
    args = [
        deps.gh_binary,
        "pr",
        "list",
        "--limit",
        "5",
        "--state",
        "all",
        "--json",
        "number,title,updatedAt,headRefName",
    ]
    result = subprocess.run(
        args,
        cwd=deps.engineer_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None

    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None

    highlights: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        updated_at = _parse_iso_datetime(str(item.get("updatedAt") or ""))
        if since is not None and updated_at is not None and updated_at < since:
            continue
        title = str(item.get("title") or "").strip()
        number = item.get("number")
        if title:
            highlights.append(f"PR #{number}: {title}")
    return PullRequestActivity(highlights=tuple(highlights[:3]), pr_count=len(highlights))


def _status_entry_in_range(
    value: datetime | None,
    since: datetime | None,
    until: datetime | None,
) -> bool:
    if value is None:
        return False
    if since is not None and value < since:
        return False
    if until is not None and value >= until:
        return False
    return True


def _parse_status_datetime(raw_value: str) -> datetime | None:
    prepared = raw_value.replace("`", "").replace(" MSK", "").strip()
    try:
        return datetime.strptime(prepared, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(DEFAULT_CONFIG.timezone))
    except ValueError:
        return None


def _classify_activity(files: tuple[str, ...]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in files:
        if path.startswith("agents/larisa_ivanovna") or path.startswith("cloudbot/workflows/larisa_"):
            counts["larisa"] += 1
        elif path.startswith("infra/orchestrator") or path.startswith("configs/schedules"):
            counts["ops"] += 1
        elif path.startswith("tests/") or path.startswith("checks/"):
            counts["quality"] += 1
        elif "/providers/" in path or path.startswith("cloudbot/providers/"):
            counts["integrations"] += 1
        elif path.startswith("docs/") or path.startswith("AGENTS.md"):
            counts["architecture"] += 1
        else:
            counts["delivery"] += 1
    return counts


def _build_themes(
    area_counts: Counter[str],
    git_activity: GitActivity,
    status_activity: StatusActivity,
    tasks_activity: TasksActivity,
    pr_activity: PullRequestActivity,
) -> tuple[ContentTheme, ...]:
    if (
        not git_activity.commit_count
        and not status_activity.entry_count
        and not tasks_activity.task_count
        and not pr_activity.pr_count
    ):
        return tuple()

    templates = [
        (
            "larisa",
            ContentTheme(
                id="larisa-workflow",
                title="Почему не каждому новому сценарию нужен новый бот",
                angle="Показывает, как растить систему через внутренние контуры, а не раздувать внешний зоопарк интерфейсов.",
                audience="руководители, product owners, founders",
                format="личное наблюдение + практический вывод",
            ),
        ),
        (
            "ops",
            ContentTheme(
                id="ops-automation",
                title="Где на самом деле ломается операционка, когда процессы идут каждый день",
                angle="Сильная тема про повторяемые процессы, ручной хаос и цену маленьких ошибок в ежедневной рутине.",
                audience="руководители агентств, операционные команды, founders",
                format="разбор с выводами",
            ),
        ),
        (
            "quality",
            ContentTheme(
                id="quality-guardrails",
                title="Почему маленькие изменения часто ломают процессы сильнее, чем большие",
                angle="Хороший заход на тему дисциплины: быстрые правки без проверки бьют по управляемости сильнее, чем кажется.",
                audience="тимлиды, операционные менеджеры, founders",
                format="экспертный пост с позицией",
            ),
        ),
        (
            "integrations",
            ContentTheme(
                id="integrations-fragility",
                title="Почему хрупкость обычно прячется на стыке систем, а не внутри одной команды",
                angle="Даёт хороший управленческий и практический взгляд на интеграции, ответственность и точки контроля.",
                audience="agency owners, ops, technical managers",
                format="behind-the-scenes с выводом",
            ),
        ),
        (
            "architecture",
            ContentTheme(
                id="architecture-runbook",
                title="Почему важные решения нужно выносить из головы в систему",
                angle="Тема про управляемость: решение, проверка и следующий шаг должны жить не в памяти человека, а в общем контуре.",
                audience="руководители, project owners, операционные команды",
                format="короткая заметка с наблюдением",
            ),
        ),
        (
            "delivery",
            ContentTheme(
                id="delivery-storytelling",
                title="Как из обычной рабочей недели вытаскивать темы для сильных постов",
                angle="Полезный мета-угол: не ждать идеальный кейс, а учиться замечать содержательные сигналы в рутинной работе.",
                audience="авторы экспертных каналов, founders, руководители",
                format="пост с тезисами",
            ),
        ),
        (
            "tasks",
            ContentTheme(
                id="tasks-signal",
                title="Почему backlog полезен не только для работы, но и для контентных инсайтов",
                angle="Показывает, где у команды реально болит и какие темы уже назрели, даже если никто ещё не сел их формулировать.",
                audience="product ops, founders, руководители команд",
                format="пост-наблюдение",
            ),
        ),
        (
            "prs",
            ContentTheme(
                id="pr-narrative",
                title="Почему PR полезны не только для ревью, но и как хроника реальных изменений",
                angle="Хороший угол на тему прозрачности: система сама оставляет след, из которого потом можно собирать narrative.",
                audience="руководители разработки, senior engineers, founders",
                format="короткий разбор",
            ),
        ),
    ]

    picked: list[ContentTheme] = []
    top_subjects = [subject for subject in git_activity.subjects if subject][:3]
    top_highlights = [item for item in status_activity.highlights if item][:2]
    task_highlights = [item for item in tasks_activity.highlights if item][:2]
    pr_highlights = [item for item in pr_activity.highlights if item][:2]
    evidence_pool = tuple(top_subjects + top_highlights + pr_highlights + task_highlights)

    if tasks_activity.task_count:
        area_counts["tasks"] += 1
    if pr_activity.pr_count:
        area_counts["prs"] += 1

    for area, theme in templates:
        if area_counts.get(area, 0) <= 0 and area not in {"delivery", "architecture"}:
            continue
        picked.append(
            ContentTheme(
                id=theme.id,
                title=theme.title,
                angle=theme.angle,
                audience=theme.audience,
                format=theme.format,
                evidence=evidence_pool[:4],
            )
        )

    if not picked and evidence_pool:
        picked.append(
            ContentTheme(
                id="fallback-story",
                title="Какие изменения за период действительно заслуживают публичного поста",
                angle="Тема опирается на уже сделанные изменения и помогает превратить внутреннюю работу в понятный нарратив.",
                audience="основатели и инженеры, которые строят публичный контур продукта",
                format="короткий пост с тезисами",
                evidence=evidence_pool[:4],
            )
        )

    return tuple(picked[:5])


def _build_summary(
    period_label: str,
    git_activity: GitActivity,
    status_activity: StatusActivity,
    tasks_activity: TasksActivity,
    pr_activity: PullRequestActivity,
    themes: tuple[ContentTheme, ...],
) -> str:
    if (
        not git_activity.commit_count
        and not status_activity.entry_count
        and not tasks_activity.task_count
        and not pr_activity.pr_count
    ):
        return f"В доступных источниках {period_label} почти нет подтверждённой фактуры."

    parts = [
        " ".join(
            [
                f"В доступных источниках {period_label} нашлось {_pluralize(git_activity.commit_count, 'commit', 'commits', 'commits')},",
                f"{status_activity.entry_count} записей STATUS,",
                f"{tasks_activity.task_count} задач и {pr_activity.pr_count} PR.",
            ]
        ),
    ]
    if themes:
        parts.append(f"Этого хватает, чтобы выделить {len(themes)} рабочих сюжетов для публикации.")
    else:
        parts.append("Но пока сигнал слишком слабый для уверенных публичных тем.")
    return " ".join(parts)


def _pluralize(value: int, one: str, few: str, many: str) -> str:
    if value % 10 == 1 and value % 100 != 11:
        suffix = one
    elif value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        suffix = few
    else:
        suffix = many
    return f"{value} {suffix}"


def _parse_iso_datetime(raw_value: str) -> datetime | None:
    prepared = str(raw_value or "").strip()
    if not prepared:
        return None
    try:
        return datetime.fromisoformat(prepared.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_belberry_hook(theme: ContentTheme, *, tone: str = "default") -> str:
    if tone == "harder":
        if "бот" in theme.title.lower():
            return "Жёсткий вывод: новый бот часто нужен тем, кто не хочет разбираться в процессе."
        if "решени" in theme.title.lower() or "систем" in theme.title.lower():
            return "Жёсткий вывод: пока решения живут в головах, у вас не система, а ручной режим."
        return f"{theme.title}. Если говорить жёстко, то проблема здесь не в инструменте, а в зрелости процесса."
    if tone == "softer":
        if "бот" in theme.title.lower():
            return "Есть наблюдение: новому сценарию не всегда нужен отдельный бот."
        if "решени" in theme.title.lower() or "систем" in theme.title.lower():
            return "Поймал себя на мысли: важные решения лучше работают, когда они вынесены в общий контур."
        return f"{theme.title}. Кажется, именно в таких деталях и собирается зрелый процесс."
    if tone == "business":
        if "бот" in theme.title.lower():
            return "Если смотреть с позиции бизнеса, лишние сущности почти всегда повышают стоимость управления."
        if "решени" in theme.title.lower() or "систем" in theme.title.lower():
            return "Для бизнеса это простая история: всё, что не зафиксировано в системе, плохо масштабируется."
        return f"{theme.title}. Если переводить это на язык бизнеса, разговор идёт про управляемость и цену ошибки."
    if "бот" in theme.title.lower():
        return "Неочевидная мысль: новому сценарию почти никогда не нужен новый бот."
    if "решени" in theme.title.lower() or "систем" in theme.title.lower():
        return "Неудобная правда: пока важные решения живут в головах, процесс вам не принадлежит."
    if "операцион" in theme.title.lower() or "операционка" in theme.title.lower():
        return "Самые дорогие проблемы обычно выглядят как невинная операционка."
    if "backlog" in theme.title.lower():
        return "Кстати, backlog полезен не только для планирования."
    return f"{theme.title}. Есть ощущение, что именно в таких деталях и проявляется зрелость процесса."


def _normalize_tone(tone: str) -> str:
    normalized = str(tone or "default").strip().lower()
    if normalized in {"harder", "softer", "business"}:
        return normalized
    return "default"


def _build_outline(tone: str) -> tuple[str, ...]:
    if tone == "business":
        return (
            "Где в процессе терялись деньги, время или управляемость.",
            "Какой контур или правило мы ввели вместо ручного режима.",
            "Как это влияет на скорость, прозрачность и повторяемость.",
            "Какой бизнес-вывод из этого стоит забрать.",
        )
    return (
        "Какая неудобная или неочевидная проблема стояла за этим изменением.",
        "Что мы поменяли в процессе или контуре, а не только в инструменте.",
        "Почему это важно для управляемости, сервиса или результата.",
        "Какой практический вывод можно забрать себе в работу.",
    )


def _build_post_text(theme: ContentTheme, *, hook: str, tone: str, evidence_block: str) -> str:
    if tone == "harder":
        middle = [
            "Такие вещи многие привыкли считать мелочью. А потом именно они начинают жрать время команды и ломать управляемость.",
            f"Здесь история была про следующее: {theme.angle}",
            "",
            "Что сделали по сути:",
            "Не стали лечить симптом очередной новой сущностью. Вместо этого оформили повторяющийся сценарий в отдельный управляемый контур.",
            "Именно это обычно и отличает рабочую систему от бесконечного набора ручных договорённостей.",
            "",
            "Если коротко:",
            "1. Повторяющийся хаос нельзя чинить вручную бесконечно.",
            "2. Если решение нельзя проверить, оно почти наверняка начнёт расползаться.",
            "3. Контент без реальной фактуры быстро превращается в пустой шум.",
        ]
        closing = "Самое неприятное в таких историях то, что цена хаоса почти всегда становится заметной слишком поздно."
    elif tone == "softer":
        middle = [
            "Мне нравятся такие истории тем, что они редко выглядят большими. Но именно из них потом и складывается ощущение порядка в системе.",
            f"Здесь мысль была довольно простая: {theme.angle}",
            "",
            "Что сделали по сути:",
            "Аккуратно вынесли повторяющийся сценарий в отдельный контур и тем самым снизили зависимость от ручного ведения.",
            "",
            "Что из этого можно взять себе:",
            "1. Повторяемые вещи лучше оформлять в правила и сценарии.",
            "2. Общий контур почти всегда полезнее, чем ещё одна отдельная сущность.",
            "3. Из спокойной операционной фактуры часто рождаются самые сильные наблюдения.",
        ]
        closing = "Наверное, в этом и есть взросление процесса: меньше шума, больше понятных повторяемых действий."
    elif tone == "business":
        middle = [
            "Если смотреть не как инженер, а как руководитель, тут разговор вообще не про инструменты.",
            "Тут разговор про стоимость управления, прозрачность и повторяемость результата.",
            f"В нашей ситуации это выглядело так: {theme.angle}",
            "",
            "Что сделали по сути:",
            "Убрали лишнюю внешнюю сущность и оформили сценарий внутри действующей системы, чтобы снизить операционные издержки и не плодить новый слой управления.",
            "",
            "Что из этого важно для бизнеса:",
            "1. Чем больше лишних сущностей, тем выше стоимость сопровождения.",
            "2. Всё, что нельзя быстро проверить и объяснить, плохо масштабируется.",
            "3. Контент и маркетинговые смыслы лучше рождаются из реальных процессов, чем из придуманных тезисов.",
        ]
        closing = "В конечном счёте это история не про автоматизацию как таковую, а про то, как делать систему дешевле в управлении и понятнее для команды."
    else:
        middle = [
            "Поймал себя на мысли, что многие такие истории снаружи выглядят как мелкая операционка.",
            "Но на практике именно в таких местах обычно и сидит либо будущий рост, либо будущая проблема.",
            f"У нас фокус был такой: {theme.angle}",
            "",
            "Что сделали по сути:",
            "Не стали плодить новые сущности снаружи и вместо этого собрали отдельный управляемый контур внутри действующей системы.",
            "Такой подход мне нравится больше, чем очередное быстрое костыльное решение, потому что потом это легче масштабировать, проверять и объяснять команде.",
            "",
            "Что из этого стоит забрать себе, коллеги:",
            "1. Если процесс повторяется, его нужно оформлять в отдельный контур, а не держать на ручном управлении.",
            "2. Если решение нельзя быстро объяснить через фактуру и понятные правила, значит контур ещё сырой.",
            "3. Контент лучше рождается не из фантазии, а из наблюдений, цифр и реальных изменений в работе.",
        ]
        closing = "Вообще всё это хорошо напоминает простую вещь: сильный результат обычно появляется не там, где мы сделали ещё один красивый шаг, а там, где убрали хаос из повторяющегося процесса."

    return "\n".join(
        [
            hook,
            "",
            *middle,
            "",
            "Фактура, на которую опирается тема:",
            evidence_block or "- Подтверждённые изменения за период без лишних домыслов.",
            "",
            closing,
        ]
    )
