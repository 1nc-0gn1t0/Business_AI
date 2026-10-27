# DESIGN-01 · Hackathon Product Experience

Дата реализации: 27–28.10.2026. Основа: main `d270675511fe44c5fbb41ed6e63c6c8bfc4f150e`,
PR26 merged. Ветка `codex/DESIGN-01-product-redesign`.

## Решение и границы

По прямому решению владельца приоритет смещён с дальнейшего hardening на
демонстрационный пользовательский опыт. Это практическая часть UX-01/02 и UI-01,
**не завершение всех этих карточек**, H-FINAL или BA-017/018. Security release
baseline H-06-FU остаётся OPEN; DESIGN-01 не принимает native Critical/High.
Backend, API/DTO, миграции, расчёты, scoring, provenance, ownership, consent,
CAS/idempotency, LLM orchestration и backup/restore не изменены.

## Карта существующих функций → новая композиция

| Экран | Реализация / API | Пользовательский результат и честное ограничение |
|---|---|---|
| Обзор | Home, существующие POST conversations/messages и consent API | Настоящее поле идеи; примеры только заполняют поле, не отправляют запрос. Обработка/ошибка/повтор; отдельное согласие. |
| AI-помощник | Chat + BusinessProfilePanel; messages/history, PATCH profile, POST profile/confirm | Диалог слева, редактируемый профиль справа; подтверждение на сервере. После подтверждения открываются локации. |
| Локации | Locations/GeoMap; geo/datasets, pois, districts, rankings | Список зон слева и настоящая MapLibre справа; карточка/маркер синхронны. Отсутствующие данные не заменяются маркерами. |
| Сравнение | Тот же результат BA-008, отдельная композиция карточек | Исходные факторы, баллы, выбор, объяснения, ограничения и параметры пересчёта; не свободные помещения. |
| Финансы | Finance/FinanceChart, POST finance/calculate | Результаты выше редактируемых вводных: капитал, три сценария, графики, sensitivity. Все цифры результата из API. |
| Возможности ВТБ | BankProducts/LeadFlow, catalogue/matches/consents/leads | Добровольные потребности, карточки и причины, демо-каталог, раздельные согласия, локальная квитанция. Нет реальной банковской интеграции. |
| Отчёт | ProjectOverview + прежний ReportExport, POST reports, GET report PDF/JSON | Только фактически выполненные разделы, ссылки назад; PDF/JSON из прежнего immutable snapshot. Экспорт не инициирует заявку. |

Пешеходный анализ вынесен в раскрываемую секцию под картой; источники и методология
доступны через disclosures. Старый scoring не заменён сетевым молча. Источники
BA-014 сохраняют явный выбор demo и ограничения покрытия.

## Пользовательский маршрут и состояние

1. Новая вкладка → короткий обзор → идея → отдельное согласие → отправка.
2. Qwen задаёт уточнения; пользователь проверяет/исправляет профиль и подтверждает.
3. Карта → поиск зон → выбор на карте или в списке → сравнение → финансы.
4. Пользователь явно загружает редактируемые **синтетические** вводные кофейни,
   рассчитывает и при необходимости изменяет их. Это не модель для любой отрасли.
5. Продукты/демо-заявка — необязательная ветка. От неё можно сразу перейти к отчёту.
6. Итоговый экран перечисляет готовые/отсутствующие разделы и позволяет скачать PDF/JSON.

Навигация доступна всегда; серверные условия выполнения операций сохранены.
`aria-current=step`, breadcrumb и профиль дают контекст. При переходе фокус
перемещается на main; пропуск навигации доступен с клавиатуры.

Один draft в App сохраняет неотправленный текст между обзором и чатом и при
отказе API; после успеха очищается. Analytics-компоненты остаются mounted/hidden,
чтобы переходы не стирали форму/расчёт. Выбор зоны/изменение версии профиля по
прежним key/CAS-инвариантам сбрасывают зависимые результаты. Гостевой credential
остаётся в sessionStorage и HTTP-заголовках, не в URL.
При reload восстанавливаются серверные профиль и история, открывается чат.
Гео/финансовые UI-вводные остаются в памяти вкладки: полное долговременное
восстановление всех шагов не реализовывалось. Изменение контекста делает
подготовленный отчёт устаревшим; старый snapshot не переписывается.

## Дизайн-система и контракты

Без UI-фреймворка и новых runtime npm-зависимостей. `ProductUI.tsx` содержит
собственную линейную SVG-иконографику, StatusBadge, Home и ProjectOverview.
Home получает controlled draft/onDraft, async onSend, busy, consent, conversation,
onResume; финансовые/геоданные не рассчитывает. Overview получает готовые
ranking/finance/bank и onOpen; отсутствие результата не превращается в ноль.
BusinessProfilePanel использует прежний ProfileEditor и onPatch/onConfirm.

CSS заменён слоями, импортируемыми через style.css, без старого слоя overrides:

- `design-tokens.css`: palette, typography, controls, focus, badges/alerts/empty.
- `product-shell.css`: sidebar/header, overview, chat/profile.
- `analysis.css`: map/zones, comparison, finance, bank/lead, provenance/report.
- `responsive.css`: последовательная адаптация композиций.

| Токен/принцип | Значение |
|---|---|
| Canvas / surface | #f4f7fb / #fff |
| Основной текст / sidebar | #192d48 / #102646 |
| Primary / secondary | #1465df / #087d79 |
| Border / radius | #dce4ef / 14px |
| Spacing | 4, 8, 12, 16, 24, 32px |
| Typography | Локальный Golos Text variable 400–900, Segoe UI fallback |
| Desktop / tablet / mobile | 224px sidebar; при ≤1000px компактная rail; при ≤600px горизонтальная навигация |
| Дополнительные границы | 1200px для плотных панелей, 1650px для широкого экрана |
| Motion | Только короткие состояния; prefers-reduced-motion отключает переходы |

Golos Text взят из [официального Google Fonts repository](https://github.com/google/fonts/tree/main/ofl/golostext),
поставляется с [OFL 1.1](../../apps/web/public/fonts/OFL.txt) и copyright.
SHA-256 `17bb58fb69aec2dfb047a2ebf52534023e9b688c97a6b7ac795b0a72912c2063`.
Никаких CDN-запросов шрифта, защищённых логотипов ВТБ или заявления об официальном
банковском сервисе. SVG favicon собственный. OSM attribution сохранена.

Loading/busy/empty/error/confirmed/stale — содержательные состояния прежних API.
422/413/429/LLM errors/correlation ID используют существующий errorText.
Никакие API-ошибки не подменяются заранее записанным успешным результатом.
Таблица sensitivity прокручивается внутри панели; fingerprint квитанции переносится.

## Проверки реализации

| Проверка | Фактический результат |
|---|---|
| Vitest | 48 PASS: прежние45 +3 проверки overview/draft/retry/empty results |
| Chromium mocked E2E | 30 PASS: прежние27 +3 сценария 1440/768/390; сохранены assertions безопасности и ошибок |
| Backend, затронутые контракты | 59 PASS: test_conversation, test_finance, test_reporting |
| ESLint / TypeScript / production build | PASS; bundle warning >500kB остаётся, не подавлялся |
| Реальные API в браузере | Qwen → профиль → PostGIS → compare → finance → bank → report PDF/JSON PASS; подробнее ниже |
| Firefox / WebKit | НЕ запускались: браузеры не установлены. Это не PASS. |
| Формальная WCAG 2.2 AA / usability study | Не проводились; focus/landmarks/labels/reduced motion и ширины проверены, сертификация не заявляется |
| Full H-regression / image scanning / full LLM eval | Не повторялись: вне DESIGN-01, продуктовые backend-контракты не менялись |

Финальный prek:7/7 hooks PASS (Ruff, formatting, mypy, pytest, ESLint, TS, Vitest).
Финальный build PASS; Chromium30/30 PASS за34.6s. CI после push проверяется отдельно.
Первый прогон выявил реальные ошибки mobile overflow таблицы и длинного fingerprint,
а также устаревшие ожидания навигации. Исправлены причины; проверки не удалены.
Для новой lazy map/нового проекта тесты явно выбирают экран. Live spec адаптирован
к автопереходу после confirm и disclosure walking; весь старый длинный live spec
повторно не запускался, вместо него выполнен описанный ниже настоящий UI smoke.

## Настоящий браузерный smoke, 27.10.2026

Новый Vite на `127.0.0.1:5174` → существующий backend `8000`, PostgreSQL17.5 /
PostGIS3.5.2, Ollama0.40.8 и установленная локальная Qwen4B.
Рабочие Docker images/PGDATA не обновлялись. Это проверка frontend с существующим
runtime, не подтверждение deployment новых H-06-FU images. Создана только новая
демонстрационная гостевая сессия; существующие пользовательские данные не очищались.
В live браузере нет route mocks, HAR/trace/video или токенов в артефактах.

- Два настоящих обращения к Qwen: «Хочу открыть кофейню в Казани. Бюджет — 2 миллиона
  рублей», затем «Формат: небольшая кофейня навынос. Источник средств: собственные средства».
  Получены кофейня/Казань/2млн/навынос/own_funds, серверное подтверждение профиля v3.
- OSM набор23 852POI; на карте ограниченная выборка500, пять зон. Переключение зоны
  через marker/card и сравнение проверены; баллы85.6/44.4 — геопризнаки, не прибыльность.
- Catchment HTTP200 от центра имеющегося графа: 41 640отрезков, 612компонентов;
  ограничения графа остаются видимыми. Он рассчитан после первого report snapshot,
  поэтому тот snapshot честно отмечает walking как отсутствующий.
- Finance: синтетический капитал1.8млн, бюджет2млн; исходные результаты −30 000 /
  285 000 / 628 200₽. Изменение аренды80 000→90 000 и настоящий POST пересчёта:
  базовый результат275 000₽. Возврат на экран сохраняет аренду90000.
- Bank matching: шесть демо-карточек, credit decision не оценивается. На новой
  сессии отказ от marketing + отдельное grant demo-lead → preview → confirm →
  server mock receipt «Демонстрационная заявка создана. Данные в ВТБ не отправлены».
- PDF53 940bytes,10pages; JSON128 526bytes скачаны непосредственно кнопками браузера.
  Кириллица извлекается. JSON SHA-256
  `8bfabc7cf6da24a5c64ff893301b422e0cc063a9351078c4a0be29506fde79c0`;
  PDF SHA-256 `93bbd969f3da06326c46216a4334931d1fa27568c1276405e0d24b677ea17826`.
  Чат/токены не экспортировались. Оба формата одного report id и профиля v3.
- На 768/390 проверены navigation/draft/no horizontal overflow; реальный mobile
  mock receipt также без overflow. В новом browser context после исправления favicon
  нет console errors; начальный404 favicon обнаружен и исправлен собственным SVG.

## Скриншоты и воспроизведение

[Реальные screenshots](../qa/design-01/): 01-home-desktop,02-chat-desktop,
03-map-desktop,04-comparison-desktop,05-finance-desktop,06-bank-desktop,
07-report-desktop,08-chat-tablet,09-chat-mobile,10-finance-mobile,
11-map-mobile,12-home-mobile,13-mock-receipt-mobile. Это actual UI screenshots,
не изображения дизайн-концепции. Finance05 и mobile10 — после пересчёта аренды90000.

Для уже работающего API используйте `npm --prefix apps/web ci`, затем
`npm --prefix apps/web run dev -- --port 5174 --strictPort`. Proxy по умолчанию8000;
другой backend задаётся `BA_TEST_API_URL`. Начните с пустой вкладки/новой гостевой
сессии, подтвердите отдельное согласие, выполните маршрут выше. Не запускайте новый
Compose поверх старого PGDATA: сначала отдельная разрешённая процедура H-06-FU.
Проверки: `npm --prefix apps/web test`, `npm --prefix apps/web run test:e2e`,
`npm --prefix apps/web run lint`, `npm --prefix apps/web run typecheck`,
`npm --prefix apps/web run build`, `prek run --all-files`.
Mock E2E не требуют GPU/LLM/БД/тайлов; основной live smoke требует реальные сервисы.

## Оставшиеся ограничения / следующий согласуемый этап

Нет новой универсальности городов/отраслей, реальных рыночных цен, кредитного
одобрения, долговременного сохранения всех UI-вводных, полного accessibility audit
или нескольких браузеров. Нужны usability-проверка с человеком, Firefox/WebKit,
проверка контраста и touch targets, затем отдельно согласованные UX/U/UI карточки.
MapLibre остаётся в большом initial bundle (~1.43MB minified); code splitting —
следующая небольшая оптимизация, предупреждение build не скрывается.
Дизайн не означает production readiness или устранение security baseline blockers.
