# Belberry «Командный центр» — UI Kit / дизайн-система

> **Назначение этого файла.** Это переносимая спецификация визуального стиля нашего внутреннего
> веб-приложения (Sales Command Center). Скормите её ИИ-ассистенту (Claude / ChatGPT / Cursor)
> вместе с задачей «свёрстай интерфейс почтового сервера в этом стиле» — и он воспроизведёт наш
> фирменный вид: тёмно-индиговый рельс-меню слева, светлое полотно, карточки со скруглениями,
> акцентный фиолет, шрифт Inter.
>
> Стиль — «спокойный Apple-минимализм + фирменный индиго Belberry». Воздух, мягкие тени,
> крупные радиусы, табличные цифры, никакого визуального шума.

---

## 0. Инструкция для ИИ (прочитай первым)

Тебе дают этот файл, чтобы ты сверстал новый интерфейс **в единой стилистике** с уже существующим
дашбордом. Правила:

1. **Бери токены из раздела 1 как есть.** Не подбирай «похожие» цвета — копируй CSS-переменные
   из блока `:root` дословно. Палитра, шрифт, радиусы и тени — единый источник правды.
2. **Шрифт — только Inter** (подключение в разделе 1). Никаких других гарнитур.
3. **Структура страницы фиксирована:** слева тёмный «рельс» (`.bb-rail`) фиксированной ширины
   248px, справа светлое прокручиваемое «полотно» (`.bb-page`, max-width 1080px, центрировано).
   На мобайле рельс превращается в верхнюю полосу (медиазапросы уже в CSS).
4. **Собирай интерфейс из готовых компонентов** раздела 3 (карточка, hero, таблица, бейджи,
   строка-список, кнопки). Не изобретай новые паттерны без необходимости — переиспользуй классы
   с префиксом `bb-`.
5. **Любой блок-секция** = `.bb-card` с шапкой `.bb-sect-head` (иконка-квадрат + заголовок +
   опциональная подпись справа).
6. **Цифры** оборачивай в `class="tabular"` (моноширинные цифры) — суммы, счётчики, проценты.
7. **Доступность:** контраст текста к фону держи как в токенах (чернила `--bb-ink` на белом/канвасе),
   интерактивные элементы — с hover-состоянием, анимации отключаются при `prefers-reduced-motion`.
8. **Не тащи тяжёлые зависимости.** Весь стиль — это чистый CSS + иконки (мы используем `lucide`,
   но подойдут любые тонкие line-иконки 18–20px, strokeWidth 2).
9. Готовый, проверяемый шаблон целиком — в разделе 4. Начинай с него, заменяя контент.

Контекст применения здесь — **почтовый сервер** (вебмейл): слева вместо разделов дашборда — папки
(Входящие, Отправленные, Черновики…), в полотне — список писем (таблица) и просмотр письма.
Раздел 4 уже показывает именно этот сценарий.

---

## 1. Дизайн-токены (копировать дословно)

Подключение шрифта (в `<head>` или первой строкой CSS):

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
```

Корневые переменные:

```css
:root {
  /* Брендовая палитра «Командный центр» */
  --bb-indigo:      #2b2a5e;  /* тёмный индиго — рельс, hero, заголовки-акценты */
  --bb-indigo-2:    #1f1e47;  /* нижняя точка градиента рельса */
  --bb-violet:      #5b50d6;  /* основной акцент — ссылки, активные состояния, бары */
  --bb-violet-soft: #f0eefb;  /* мягкий фиолет — фон иконок-квадратов, hover строк, бейджи */
  --bb-canvas:      #faf8f5;  /* тёплый «бумажный» фон полотна */
  --bb-ink:         #1d1d1f;  /* основной текст (Apple-чернила) */
  --bb-muted:       #6e6e73;  /* вторичный текст */
  --bb-faint:       #9a9aa0;  /* третичный текст, подписи, плейсхолдеры */
  --bb-line:        #ece8e3;  /* hairline-границы, разделители */

  /* Семафор статусов */
  --bb-red:   #d4202e;  /* критично / отказ / «горит» */
  --bb-amber: #e88a3b;  /* внимание / предупреждение */
  --bb-green: #2c7a4a;  /* успех / в норме / выполнено */

  /* Тени */
  --bb-shadow:      0 1px 3px rgba(20, 18, 50, 0.06), 0 8px 24px -12px rgba(20, 18, 50, 0.12);
  --bb-shadow-lift: 0 1px 3px rgba(20, 18, 50, 0.06), 0 16px 34px -16px rgba(43, 42, 94, 0.4);

  /* Радиусы: карточки 18px, hero 24px, кнопки/инпуты 10–12px, пилюли 999px */
  --bb-radius-card: 18px;
  --bb-radius-hero: 24px;
}
```

Базовая типографика и фон:

```css
body {
  margin: 0;
  min-height: 100vh;
  background: var(--bb-canvas);
  color: var(--bb-ink);
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
  letter-spacing: -0.01em;          /* фирменный лёгкий «минус-трекинг» */
}
h1, h2, h3, h4 { font-weight: 600; letter-spacing: -0.022em; }
.tabular { font-variant-numeric: tabular-nums; }  /* для всех цифр */
```

### Шпаргалка по применению цвета

| Где | Токен |
|-----|-------|
| Фон страницы | `--bb-canvas` `#faf8f5` |
| Фон карточек, попапов | `#ffffff` |
| Рельс-меню (градиент) | `--bb-indigo` → `--bb-indigo-2` |
| Основной текст | `--bb-ink` `#1d1d1f` |
| Подписи, мета | `--bb-muted` / `--bb-faint` |
| Ссылки, активное, прогресс-бары | `--bb-violet` `#5b50d6` |
| Фон иконок-секций, hover строк, лёгкие бейджи | `--bb-violet-soft` `#f0eefb` |
| Границы, разделители | `--bb-line` `#ece8e3` |
| Критично / ошибка | `--bb-red` `#d4202e` |
| Внимание | `--bb-amber` `#e88a3b` |
| Успех | `--bb-green` `#2c7a4a` |

---

## 2. Сетка и каркас страницы

Корневой layout — флекс-строка: рельс + полотно.

```html
<div style="display:flex; min-height:100vh;">
  <aside class="bb-rail"> … меню … </aside>
  <main style="flex:1; min-width:0;">
    <div class="bb-page"> … контент … </div>
  </main>
</div>
```

```css
/* Тёмный индиго-рельс слева */
.bb-rail {
  position: sticky; top: 0; height: 100vh; width: 248px; flex: 0 0 248px;
  background: linear-gradient(180deg, var(--bb-indigo) 0%, var(--bb-indigo-2) 100%);
  color: #cfcce8; display: flex; flex-direction: column; padding: 18px 14px; overflow: hidden;
}
/* Светлое полотно справа */
.bb-page { max-width: 1080px; margin: 0 auto; padding: 34px 34px 70px; }

/* Сетка карточек */
.bb-grid   { display: grid; gap: 16px; }
.bb-grid-4 { grid-template-columns: repeat(4, 1fr); }
@media (max-width: 900px) { .bb-grid-4 { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 520px) { .bb-grid-4, .bb-grid { grid-template-columns: 1fr !important; } }
```

Мобильная адаптация рельса (рельс → верхняя полоса):

```css
@media (max-width: 760px) {
  .bb-rail { position: static; width: 100%; height: auto; flex-direction: row;
    align-items: center; flex: none; padding: 10px 14px; gap: 10px; }
  .bb-nav { flex-direction: row; flex: 1; gap: 4px; overflow-x: auto; }
}
@media (max-width: 600px) { .bb-page { padding: 18px 16px 56px; } }
```

---

## 3. Компоненты (рецепты)

Каждый блок — копипаст HTML + CSS. Все классы с префиксом `bb-`.

### 3.1 Рельс-меню (навигация)

```html
<aside class="bb-rail">
  <div class="bb-rail-glow" aria-hidden></div>

  <div class="bb-brand">
    <img src="/logo.svg" alt="Belberry" class="bb-brand-img" />
    <small class="bb-brand-tag">Почта</small>
  </div>

  <nav class="bb-nav">
    <div class="bb-nav-label">Папки</div>
    <a class="bb-nav-item active" href="#">📥 Входящие <span class="bb-nav-count">7</span></a>
    <a class="bb-nav-item" href="#">📤 Отправленные</a>
    <a class="bb-nav-item" href="#">📝 Черновики</a>
    <a class="bb-nav-item" href="#">🗑 Корзина</a>
  </nav>

  <div class="bb-rail-foot">
    <div class="bb-ava">ЕЩ</div>
    <div class="bb-who"><b>es@belberry.net</b><small>Руководитель</small></div>
    <button class="bb-logout" title="Выйти">⎋</button>
  </div>
</aside>
```

```css
.bb-rail-glow { position: absolute; inset: -40% -60% auto -40%; height: 420px; pointer-events: none;
  background: radial-gradient(closest-side, rgba(91,80,214,.55), transparent 70%); filter: blur(20px); opacity: .55; }
.bb-brand { display: flex; flex-direction: column; gap: 7px; padding: 8px 10px 22px; position: relative; }
.bb-brand-img { height: 26px; width: auto; max-width: 170px; filter: brightness(0) invert(1); opacity: .96; }
.bb-brand-tag { color: #a7a2d6; font-size: 11px; font-weight: 500; letter-spacing: .04em; padding-left: 2px; }
.bb-nav { display: flex; flex-direction: column; gap: 3px; position: relative; }
.bb-nav-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: .12em; color: #7d79b0; padding: 14px 12px 6px; }
.bb-nav-item { display: flex; align-items: center; gap: 11px; padding: 10px 12px; border-radius: 12px;
  color: #cfcce8; text-decoration: none; font-size: 14.5px; font-weight: 500; transition: background .18s, color .18s; }
.bb-nav-item:hover { background: rgba(255,255,255,.06); color: #fff; }
.bb-nav-item.active { background: linear-gradient(90deg, rgba(91,80,214,.9), rgba(91,80,214,.45));
  color: #fff; font-weight: 600; box-shadow: 0 6px 18px -8px rgba(91,80,214,.9); }
.bb-nav-count { margin-left: auto; background: var(--bb-red); color: #fff; font-size: 11px; font-weight: 700;
  border-radius: 999px; min-width: 19px; height: 19px; padding: 0 6px; display: inline-grid; place-items: center; line-height: 1; }
.bb-rail-foot { margin-top: auto; display: flex; align-items: center; gap: 10px; padding: 10px;
  border-radius: 12px; background: rgba(255,255,255,.05); }
.bb-ava { width: 34px; height: 34px; border-radius: 50%; flex: 0 0 34px;
  background: linear-gradient(135deg, #8b80ff, #5b50d6); color: #fff; display: grid; place-items: center; font-weight: 700; font-size: 13px; }
.bb-who { min-width: 0; flex: 1; }
.bb-who b { font-size: 12.5px; color: #fff; font-weight: 600; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bb-who small { color: #a7a2d6; font-weight: 500; font-size: 11px; }
.bb-logout { border: 0; background: transparent; color: #a7a2d6; cursor: pointer; padding: 6px; border-radius: 8px; }
.bb-logout:hover { background: rgba(255,255,255,.1); color: #fff; }
```

> Лого монохромное тёмно-индиговое; на тёмном рельсе делаем его белым через
> `filter: brightness(0) invert(1)`.

### 3.2 Hero-баннер (шапка раздела)

```html
<div class="bb-hero">
  <div class="bb-hero-row">
    <div>
      <div class="bb-hero-eyebrow">Почта · Belberry</div>
      <div class="bb-hero-title">Входящие</div>
      <div class="bb-hero-sub">7 непрочитанных · обновлено только что</div>
    </div>
    <a class="bb-hero-btn" href="#" style="margin-left:auto;">✏️ Написать письмо</a>
  </div>
</div>
```

```css
.bb-hero { position: relative; border-radius: 24px; padding: 26px 28px; margin-bottom: 22px;
  background: linear-gradient(135deg, var(--bb-indigo), #3a3780); color: #fff; box-shadow: var(--bb-shadow); }
.bb-hero-row { display: flex; align-items: center; gap: 28px; flex-wrap: wrap; }
.bb-hero-eyebrow { color: #c9c5f0; font-size: 13px; font-weight: 600; }
.bb-hero-title { font-size: 30px; font-weight: 800; letter-spacing: -.03em; margin-top: 4px; }
.bb-hero-sub { color: #c9c5f0; font-size: 13.5px; font-weight: 500; margin-top: 6px; }
.bb-hero-btn { display: inline-flex; align-items: center; gap: 7px; background: rgba(255,255,255,.14);
  color: #fff; border: 1px solid rgba(255,255,255,.22); border-radius: 11px; padding: 8px 14px;
  font-size: 13.5px; font-weight: 600; text-decoration: none; transition: background .15s, border-color .15s; }
.bb-hero-btn:hover { background: rgba(255,255,255,.22); border-color: rgba(255,255,255,.4); }
```

### 3.3 Карточка-секция

Базовый контейнер для любого блока контента.

```html
<section class="bb-card">
  <div class="bb-sect-head">
    <div class="bb-sect-ic">📥</div>
    <h2>Входящие</h2>
    <small>7 непрочитанных</small>
  </div>
  … содержимое …
</section>
```

```css
.bb-card { background: #fff; border: 1px solid var(--bb-line); border-radius: 18px; padding: 20px; box-shadow: var(--bb-shadow); }
.bb-sect-head { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.bb-sect-head h2 { font-size: 17px; font-weight: 700; letter-spacing: -.02em; margin: 0; }
.bb-sect-head small { color: var(--bb-faint); font-size: 12.5px; font-weight: 500; margin-left: auto; }
.bb-sect-ic { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center;
  background: var(--bb-violet-soft); color: var(--bb-violet); flex: 0 0 30px; font-size: 15px; }
```

### 3.4 Таблица

```css
.bb-table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13.5px; }
.bb-table th { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: var(--bb-faint);
  font-weight: 600; padding: 8px 10px; border-bottom: 1px solid var(--bb-line); }
.bb-table td { padding: 11px 10px; border-bottom: 1px solid var(--bb-line); color: var(--bb-ink); }
.bb-table tbody tr:last-child td { border-bottom: 0; }
.bb-table tbody tr { transition: background .12s; }
.bb-table tbody tr:hover { background: var(--bb-violet-soft); }
.bb-table .r { text-align: right; }   /* числовые колонки */
```

### 3.5 Кликабельная строка-список (письмо, контакт, элемент)

Универсальный паттерн «аватар + заголовок/подзаголовок + бар/бейдж + шеврон».

```html
<button class="bb-mrow">
  <div class="bb-mrow-ava">АИ</div>
  <div class="bb-mrow-id"><b>Анна Исаева</b><small>Бюджет на Q3</small></div>
  <span class="bb-mrow-badge">14:20</span>
  <span class="bb-mrow-chev">›</span>
</button>
```

```css
.bb-mrow { display: flex; align-items: center; gap: 13px; padding: 10px; border-radius: 12px; cursor: pointer;
  transition: background .15s; border: 0; background: transparent; width: 100%; text-align: left; font: inherit; }
.bb-mrow:hover { background: var(--bb-violet-soft); }
.bb-mrow-ava { width: 38px; height: 38px; flex: 0 0 38px; border-radius: 50%; display: grid; place-items: center;
  background: linear-gradient(135deg, #8b80ff, #5b50d6); color: #fff; font-weight: 700; font-size: 13px; }
.bb-mrow-id { min-width: 0; flex: 1; }
.bb-mrow-id b { font-size: 14px; font-weight: 600; display: block; line-height: 1.2; }
.bb-mrow-id small { font-size: 11.5px; color: var(--bb-faint); }
.bb-mrow-badge { font-size: 11.5px; font-weight: 700; border-radius: 999px; padding: 3px 9px;
  background: var(--bb-violet-soft); color: var(--bb-violet); white-space: nowrap; }
.bb-mrow-badge.hit { background: #e7f4ec; color: var(--bb-green); }
.bb-mrow-chev { color: var(--bb-faint); flex: 0 0 auto; }
```

### 3.6 Бейджи и статусы

```css
/* Лёгкий фиолетовый бейдж (по умолчанию) */
.bb-badge { font-size: 11.5px; font-weight: 700; border-radius: 999px; padding: 3px 9px;
  background: var(--bb-violet-soft); color: var(--bb-violet); white-space: nowrap; }
/* Семафорные варианты */
.bb-badge.green { background: #e7f4ec; color: var(--bb-green); }
.bb-badge.amber { background: #fdf2e7; color: #b5651d; }
.bb-badge.red   { background: #fdeced; color: var(--bb-red); }

/* Цветная полоска-приоритет слева (для строк-алертов/важных писем) */
.bb-sev { width: 4px; align-self: stretch; border-radius: 3px; flex: 0 0 4px; }
.bb-sev.critical { background: var(--bb-red); }
.bb-sev.warning  { background: var(--bb-amber); }
.bb-sev.ok       { background: var(--bb-green); }

/* Живой индикатор (мигающая точка) */
.bb-live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--bb-red);
  display: inline-block; animation: bb-pulse 1.8s infinite; }
```

### 3.7 Кнопки

```css
/* Вторичная кнопка на светлом фоне */
.bb-rbtn { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--bb-line);
  background: #fff; border-radius: 10px; padding: 7px 12px; font-size: 13px; font-weight: 600;
  color: var(--bb-ink); cursor: pointer; transition: background .15s, color .15s, border-color .15s; text-decoration: none; }
.bb-rbtn:hover { background: var(--bb-violet-soft); border-color: #d6cffb; color: var(--bb-violet); }

/* Основная (акцентная) кнопка */
.bb-btn-primary { display: inline-flex; align-items: center; gap: 7px; border: 0; border-radius: 11px;
  background: var(--bb-violet); color: #fff; padding: 9px 16px; font-size: 14px; font-weight: 600; cursor: pointer;
  box-shadow: 0 6px 18px -8px rgba(91,80,214,.9); transition: filter .15s; }
.bb-btn-primary:hover { filter: brightness(1.08); }
```

### 3.8 Прогресс-бар (план/факт, заполнение)

```css
.bb-pf-bar { height: 9px; border-radius: 6px; background: #f0ece7; overflow: hidden; margin-top: 7px; }
.bb-pf-bar i { display: block; height: 100%;
  background: linear-gradient(90deg, var(--bb-violet), var(--bb-indigo));
  transition: width .9s cubic-bezier(.22,1,.36,1); }
```

### 3.9 Анимации и микровзаимодействия

```css
@keyframes bb-fade  { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@keyframes bb-pulse { 0% { box-shadow: 0 0 0 0 rgba(212,32,46,.5); } 70% { box-shadow: 0 0 0 9px rgba(212,32,46,0); } 100% { box-shadow: 0 0 0 0 rgba(212,32,46,0); } }
.bb-fade { animation: bb-fade .35s ease; }
.bb-lift { transition: transform .2s, box-shadow .2s; }
.bb-lift:hover { transform: translateY(-3px); box-shadow: var(--bb-shadow-lift); }
@media (prefers-reduced-motion: reduce) {
  .bb-fade, .bb-live-dot { animation: none; }
  .bb-lift { transition: none; }
}
```

---

## 4. Готовый HTML-эталон (вебмейл в нашем стиле)

Самодостаточная страница: рельс с папками + список писем + просмотр письма. Открой в браузере —
увидишь целевой вид. Используй как стартовый шаблон, заменяя контент. (Тот же HTML лежит рядом
в файле `belberry-ui-kit-preview.html`.)

```html
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Belberry Mail — эталон стиля</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root{
  --bb-indigo:#2b2a5e;--bb-indigo-2:#1f1e47;--bb-violet:#5b50d6;--bb-violet-soft:#f0eefb;
  --bb-canvas:#faf8f5;--bb-ink:#1d1d1f;--bb-muted:#6e6e73;--bb-faint:#9a9aa0;--bb-line:#ece8e3;
  --bb-red:#d4202e;--bb-amber:#e88a3b;--bb-green:#2c7a4a;
  --bb-shadow:0 1px 3px rgba(20,18,50,.06),0 8px 24px -12px rgba(20,18,50,.12);
}
*{box-sizing:border-box;}
body{margin:0;min-height:100vh;background:var(--bb-canvas);color:var(--bb-ink);
  font-family:Inter,-apple-system,BlinkMacSystemFont,'SF Pro Text','Helvetica Neue',Arial,sans-serif;
  -webkit-font-smoothing:antialiased;letter-spacing:-.01em;}
h1,h2,h3,h4{font-weight:600;letter-spacing:-.022em;margin:0;}
.tabular{font-variant-numeric:tabular-nums;}
.app{display:flex;min-height:100vh;}

/* Рельс */
.bb-rail{position:sticky;top:0;height:100vh;width:248px;flex:0 0 248px;
  background:linear-gradient(180deg,var(--bb-indigo),var(--bb-indigo-2));color:#cfcce8;
  display:flex;flex-direction:column;padding:18px 14px;overflow:hidden;}
.bb-rail-glow{position:absolute;inset:-40% -60% auto -40%;height:420px;pointer-events:none;
  background:radial-gradient(closest-side,rgba(91,80,214,.55),transparent 70%);filter:blur(20px);opacity:.55;}
.bb-brand{display:flex;flex-direction:column;gap:7px;padding:8px 10px 22px;position:relative;}
.bb-brand b{font-size:18px;color:#fff;font-weight:700;letter-spacing:-.02em;}
.bb-brand-tag{color:#a7a2d6;font-size:11px;font-weight:500;letter-spacing:.04em;}
.bb-nav{display:flex;flex-direction:column;gap:3px;position:relative;}
.bb-nav-label{font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;color:#7d79b0;padding:14px 12px 6px;}
.bb-nav-item{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:12px;color:#cfcce8;
  text-decoration:none;font-size:14.5px;font-weight:500;transition:background .18s,color .18s;cursor:pointer;}
.bb-nav-item:hover{background:rgba(255,255,255,.06);color:#fff;}
.bb-nav-item.active{background:linear-gradient(90deg,rgba(91,80,214,.9),rgba(91,80,214,.45));
  color:#fff;font-weight:600;box-shadow:0 6px 18px -8px rgba(91,80,214,.9);}
.bb-nav-count{margin-left:auto;background:var(--bb-red);color:#fff;font-size:11px;font-weight:700;
  border-radius:999px;min-width:19px;height:19px;padding:0 6px;display:inline-grid;place-items:center;line-height:1;}
.bb-rail-foot{margin-top:auto;display:flex;align-items:center;gap:10px;padding:10px;border-radius:12px;background:rgba(255,255,255,.05);}
.bb-ava{width:34px;height:34px;border-radius:50%;flex:0 0 34px;background:linear-gradient(135deg,#8b80ff,#5b50d6);
  color:#fff;display:grid;place-items:center;font-weight:700;font-size:13px;}
.bb-who{min-width:0;flex:1;}
.bb-who b{font-size:12.5px;color:#fff;font-weight:600;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.bb-who small{color:#a7a2d6;font-weight:500;font-size:11px;}

/* Полотно */
.bb-page{max-width:1080px;margin:0 auto;padding:34px 34px 70px;width:100%;}
main{flex:1;min-width:0;}

/* Hero */
.bb-hero{position:relative;border-radius:24px;padding:26px 28px;margin-bottom:22px;
  background:linear-gradient(135deg,var(--bb-indigo),#3a3780);color:#fff;box-shadow:var(--bb-shadow);}
.bb-hero-row{display:flex;align-items:center;gap:28px;flex-wrap:wrap;}
.bb-hero-eyebrow{color:#c9c5f0;font-size:13px;font-weight:600;}
.bb-hero-title{font-size:30px;font-weight:800;letter-spacing:-.03em;margin-top:4px;}
.bb-hero-sub{color:#c9c5f0;font-size:13.5px;font-weight:500;margin-top:6px;}
.bb-hero-btn{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.14);color:#fff;
  border:1px solid rgba(255,255,255,.22);border-radius:11px;padding:8px 14px;font-size:13.5px;font-weight:600;
  text-decoration:none;cursor:pointer;transition:background .15s,border-color .15s;}
.bb-hero-btn:hover{background:rgba(255,255,255,.22);border-color:rgba(255,255,255,.4);}

/* Сетка / карточки */
.bb-grid{display:grid;gap:16px;grid-template-columns:1.3fr 1fr;}
@media (max-width:860px){.bb-grid{grid-template-columns:1fr;}}
.bb-card{background:#fff;border:1px solid var(--bb-line);border-radius:18px;padding:20px;box-shadow:var(--bb-shadow);}
.bb-sect-head{display:flex;align-items:center;gap:10px;margin-bottom:16px;}
.bb-sect-head h2{font-size:17px;font-weight:700;letter-spacing:-.02em;}
.bb-sect-head small{color:var(--bb-faint);font-size:12.5px;font-weight:500;margin-left:auto;}
.bb-sect-ic{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;
  background:var(--bb-violet-soft);color:var(--bb-violet);flex:0 0 30px;font-size:15px;}

/* Строки-письма */
.bb-mrow{display:flex;align-items:center;gap:13px;padding:10px;border-radius:12px;cursor:pointer;
  transition:background .15s;border:0;background:transparent;width:100%;text-align:left;font:inherit;}
.bb-mrow:hover{background:var(--bb-violet-soft);}
.bb-mrow.unread{background:#fcfbff;}
.bb-mrow-ava{width:38px;height:38px;flex:0 0 38px;border-radius:50%;display:grid;place-items:center;
  background:linear-gradient(135deg,#8b80ff,#5b50d6);color:#fff;font-weight:700;font-size:13px;}
.bb-mrow-id{min-width:0;flex:1;}
.bb-mrow-id b{font-size:14px;font-weight:600;display:block;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.bb-mrow-id small{font-size:12px;color:var(--bb-faint);display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.bb-mrow-badge{font-size:11.5px;font-weight:700;border-radius:999px;padding:3px 9px;background:var(--bb-violet-soft);color:var(--bb-violet);white-space:nowrap;}
.bb-dot{width:8px;height:8px;border-radius:50%;background:var(--bb-violet);flex:0 0 8px;}

/* Просмотр письма */
.bb-msg-head{display:flex;align-items:center;gap:13px;margin-bottom:14px;}
.bb-msg-meta{font-size:12.5px;color:var(--bb-muted);margin:10px 0 16px;}
.bb-msg-body{font-size:14.5px;line-height:1.65;color:var(--bb-ink);}
.bb-msg-body p{margin:0 0 12px;}
.bb-actions{display:flex;gap:8px;margin-top:18px;flex-wrap:wrap;}
.bb-rbtn{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--bb-line);background:#fff;border-radius:10px;
  padding:7px 12px;font-size:13px;font-weight:600;color:var(--bb-ink);cursor:pointer;transition:.15s;text-decoration:none;}
.bb-rbtn:hover{background:var(--bb-violet-soft);border-color:#d6cffb;color:var(--bb-violet);}
.bb-btn-primary{display:inline-flex;align-items:center;gap:7px;border:0;border-radius:11px;background:var(--bb-violet);
  color:#fff;padding:9px 16px;font-size:14px;font-weight:600;cursor:pointer;box-shadow:0 6px 18px -8px rgba(91,80,214,.9);}

/* Бейджи */
.bb-badge{font-size:11.5px;font-weight:700;border-radius:999px;padding:3px 9px;background:var(--bb-violet-soft);color:var(--bb-violet);}
.bb-badge.green{background:#e7f4ec;color:var(--bb-green);}
.bb-badge.amber{background:#fdf2e7;color:#b5651d;}

@media (max-width:760px){
  .bb-rail{position:static;width:100%;height:auto;flex-direction:row;align-items:center;flex:none;padding:10px 14px;gap:10px;}
  .bb-rail-glow,.bb-nav-label,.bb-rail-foot{display:none;}
  .bb-brand{padding:0;flex-direction:row;}
  .bb-nav{flex-direction:row;flex:1;gap:4px;overflow-x:auto;}
  .bb-page{padding:18px 16px 56px;}
}
</style>
</head>
<body>
<div class="app">
  <!-- РЕЛЬС -->
  <aside class="bb-rail">
    <div class="bb-rail-glow"></div>
    <div class="bb-brand">
      <b>Belberry</b>
      <span class="bb-brand-tag">Почта</span>
    </div>
    <nav class="bb-nav">
      <div class="bb-nav-label">Папки</div>
      <a class="bb-nav-item active">📥 Входящие <span class="bb-nav-count">7</span></a>
      <a class="bb-nav-item">📤 Отправленные</a>
      <a class="bb-nav-item">📝 Черновики</a>
      <a class="bb-nav-item">⭐ Важные</a>
      <a class="bb-nav-item">🗑 Корзина</a>
    </nav>
    <div class="bb-rail-foot">
      <div class="bb-ava">ЕЩ</div>
      <div class="bb-who"><b>es@belberry.net</b><small>Руководитель</small></div>
    </div>
  </aside>

  <!-- ПОЛОТНО -->
  <main>
    <div class="bb-page">
      <div class="bb-hero">
        <div class="bb-hero-row">
          <div>
            <div class="bb-hero-eyebrow">Почта · Belberry</div>
            <div class="bb-hero-title">Входящие</div>
            <div class="bb-hero-sub">7 непрочитанных · обновлено только что</div>
          </div>
          <a class="bb-hero-btn" style="margin-left:auto;">✏️ Написать письмо</a>
        </div>
      </div>

      <div class="bb-grid">
        <!-- Список писем -->
        <section class="bb-card">
          <div class="bb-sect-head">
            <div class="bb-sect-ic">📥</div>
            <h2>Входящие</h2>
            <small>сегодня</small>
          </div>

          <button class="bb-mrow unread">
            <span class="bb-dot"></span>
            <div class="bb-mrow-ava">АИ</div>
            <div class="bb-mrow-id"><b>Анна Исаева</b><small>Бюджет на Q3 — нужно согласовать</small></div>
            <span class="bb-mrow-badge">14:20</span>
          </button>

          <button class="bb-mrow unread">
            <span class="bb-dot"></span>
            <div class="bb-mrow-ava">СП</div>
            <div class="bb-mrow-id"><b>Сергей Петров</b><small>Re: договор с клиентом — правки</small></div>
            <span class="bb-mrow-badge">12:05</span>
          </button>

          <button class="bb-mrow">
            <div class="bb-mrow-ava" style="background:linear-gradient(135deg,#e88a3b,#d4202e);">Б24</div>
            <div class="bb-mrow-id"><b>Bitrix24</b><small>Отчёт по сделкам готов</small></div>
            <span class="bb-mrow-badge green">вчера</span>
          </button>

          <button class="bb-mrow">
            <div class="bb-mrow-ava">ЛИ</div>
            <div class="bb-mrow-id"><b>Лариса Ивановна</b><small>Сводка продаж за неделю</small></div>
            <span class="bb-mrow-badge">пн</span>
          </button>
        </section>

        <!-- Просмотр письма -->
        <section class="bb-card">
          <div class="bb-sect-head">
            <div class="bb-sect-ic">✉️</div>
            <h2>Письмо</h2>
            <small><span class="bb-badge amber">важное</span></small>
          </div>

          <div class="bb-msg-head">
            <div class="bb-mrow-ava">АИ</div>
            <div class="bb-mrow-id">
              <b>Анна Исаева</b>
              <small>anna@belberry.net</small>
            </div>
          </div>

          <h3 style="font-size:18px;margin-bottom:4px;">Бюджет на Q3 — нужно согласовать</h3>
          <div class="bb-msg-meta">кому: вы · сегодня в 14:20</div>

          <div class="bb-msg-body">
            <p>Привет! Подготовила черновик бюджета на третий квартал. Основные статьи без изменений,
            но по маркетингу предлагаю поднять лимит на 12% — обоснование внутри.</p>
            <p>Посмотри, пожалуйста, до пятницы. Если ок — отправлю на финальное утверждение.</p>
            <p>Спасибо!</p>
          </div>

          <div class="bb-actions">
            <button class="bb-btn-primary">↩ Ответить</button>
            <button class="bb-rbtn">↪ Переслать</button>
            <button class="bb-rbtn">🗑 В корзину</button>
          </div>
        </section>
      </div>
    </div>
  </main>
</div>
</body>
</html>
```

---

## 5. Чек-лист «попали в стиль»

- [ ] Шрифт — Inter, с лёгким `letter-spacing: -0.01em`.
- [ ] Фон страницы — тёплый `#faf8f5`, карточки — белые с радиусом 18px и мягкой тенью.
- [ ] Слева тёмно-индиговый рельс-меню (градиент), активный пункт — фиолетовая заливка.
- [ ] Акцент — фиолет `#5b50d6`: ссылки, активное, прогресс-бары, иконки-квадраты секций.
- [ ] Иконки секций — квадрат 30px со скруглением 9px, фон `#f0eefb`, иконка фиолетовая.
- [ ] Статусы строго по семафору: красный/янтарь/зелёный из токенов.
- [ ] Цифры — `tabular-nums`.
- [ ] Hover у кликабельных строк — фон `#f0eefb`.
- [ ] Мобайл: рельс сворачивается в верхнюю полосу.

---

*Источник истины: `web/src/app/globals.css` дашборда Sales Command Center. При расхождениях
приоритет у боевого CSS — этот файл его зеркалит.*
