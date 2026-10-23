# Business AI — HANDOFF

## BA-011 · 23.10.2026

- PR #10 объединён: d67a6b56a61dfc1ee1349d5f61e33e0d3ac0eaa0.
  Main синхронизирован, дерево перед началом было чистым.
- Ветка: feat/BA-011-bank-products. Фактический HEAD/PR/CI — в итоговом отчёте.
  Не объединять автоматически; BA-012 не начиналась.

## Реализовано

- app/bank: schemas.py, catalogue.json, matching.py — Product, EligibilityRule,
  EvidenceSource/review dates, локальный версионируемый JSON и чистый matcher.
- Шесть demo-карточек: РКО, регистрация, торговый/интернет-эквайринг,
  дебетовая бизнес-карта, справка о финансировании. Никаких выдуманных тарифов.
- Трёхзначный AND: matched/unknown/not_matched. Unknown требует уточнения,
  явное несовпадение исключает карточку. Stale/future/retired/unavailable блокируются.
  Trace: исходные параметры/интерпретация, rule, input_path, sources, ограничения.
- GET /api/v1/bank-products; POST /api/v1/conversations/{id}/bank-products/matches.
  Matching читает настоящий профиль из PostgreSQL с X-Conversation-Token,
  expected_version и catalogue_fingerprint. Client profile/confirmed/as_of не принимаются.
  Read-only: профиль/история не меняются; 401/404/409/422/503 обработаны.
- BankProducts.tsx: добровольные потребности, demo-статусы, причины/вопросы,
  официальные ссылки и даты, правила/версии. Изменение needs/профиля/каталога
  снимает старые результаты. Дополнительные needs — только в памяти вкладки.
- Qwen/гео/финансовые алгоритмы сохранены; новых зависимостей и миграций нет.
  Нет кредитного score, банковской интеграции, заявок или receipts BA-012.
- README, BANK_CATALOGUE.md, ADR-0007, UI docs; offline demo fixture
  docs/examples/BA-011-coffee.json; настоящие browser screenshots/verification BA-011.

## Источники и ограничения

23.10.2026 просмотрены индексированные официальные страницы ВТБ:
/malyj-biznes/ru/rko/, /registraciya/, /acquiring/, /acquiring/internet-acquiring/,
/biznes-karty/, /kredity-i-garantii/ (последние пути после /malyj-biznes/).
Прямой web fetch давал 502, urllib/PowerShell — ошибку TLS-цепочки.
Сертификаты/системные настройки не менялись, TLS-проверка не отключалась.
Это не доказательство недоступности ВТБ и не проверка действующих условий.

Начальный каталог: demonstration/unconfirmed, источники cached_only,
last_verified_at/digest=null. Review date — попытка проверки. Recommended_ids пуст;
совпадения отдельно в demonstration_ids. Срок пересмотра 30 дней, потом блокировка.
Для public_reference/published нужны ответственная прямая проверка, дата/digest,
уточнённые условия и verified source. См. BANK_CATALOGUE.md для обновления JSON/volume.

## Пример кофейни: Казань, 2 млн ₽

- Только профиль: нужны уточнения, автоматических совпадений нет.
- Явно ИП + офлайн + приём карт + нужен счёт/дебетовая карта:
  три demo_match — vtb-rko, vtb-merchant-acquiring, vtb-business-card.
- Онлайн меняет тип эквайринга; до регистрации, на стадии подготовки с запросом
  помощи — demo регистрации. Unknown не считается ИП или выполненным условием.
- Финансирование только как информация при интересе; loan/mixed используется
  лишь если отдельного ответа нет. Явное «нет» приоритетно. Credit_decision=not_assessed.
- Бюджет/категория/город не доказывают MCC-допуск, тариф и кредитоспособность.
  Банковская маржа, OSM-score, стиль речи и LLM не участвуют в подборе.

## Проверки

- pytest apps/api/tests/test_bank.py -q: 23 unit/API PASS — matching/unknown,
  demo/verified fixtures, stale/retired/unconfirmed/unavailable, trace/replay,
  строгая валидация, guest/version/catalogue pin и безопасный 503.
- npm --prefix apps/web test: 21 PASS, включая 5 банковских тестов.
- npm --prefix apps/web run test:e2e: 3 mock Chromium-сценария PASS,
  без сети банка, GPU и весов; существующий BA-010 сценарий сохранён.
- docker compose --profile test run --build --rm db-tests: 50 PASS,
  в том числе новый protected matching/confirm/version/чужой ключ/отсутствие мутаций.
- prek run --all-files: Ruff/format/mypy/pytest/ESLint/TypeScript/frontend tests PASS;
  production build PASS (прежнее предупреждение о размере MapLibre chunk).
- Docker Compose healthy, scripts/smoke.ps1 PASS; volumes/данные сохранены.
- Настоящий browser workflow BA010_REAL=1 + BA010_ARTIFACT_DIR=test-results/ba011-regression:
  Qwen → профиль → реальные зоны → финансы/пересчёт → банковский API/demo/mobile;
  PASS, без console/page errors. Это проверка нашего API, не интеграции ВТБ.
  Дата/факты: docs/screenshots/BA-011-verification.json, снимки BA-011-bank*.png.
- Работали через штатное разрешение вне песочницы; pytest использует отдельный
  PYTEST_DEBUG_TEMPROOT. Traces/HAR/video с ключами не записывались.

## Следующее действие

1. Владелец проверяет PR BA-011/CI и решает о merge.
2. Для действующих рекомендаций — проверка/обновление источников и каталога.
3. BA-012 (consent/mock lead) только по отдельному разрешению. Дополнительные
   needs не сохраняются в DB/LLM; актуальные тарифы, банк и Firefox/Safari не проверены.
