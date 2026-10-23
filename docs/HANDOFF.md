# Business AI — HANDOFF

## BA-012 · 23.10.2026

- PR #11 объединён: 61ef7d809d94bf15ac35ac621e9ad47ceea54d13.
  Main обновлён ff-only, дерево до начала чистое.
- Ветка feat/BA-012-consent-mock-lead. Фактический HEAD/PR/CI — в итоговом отчёте.
  PR не объединять автоматически. BA-013 не начиналась.

## Реализовано

- app/leads: схемы, политика трёх независимых согласий, сервис и Protocol mock adapter;
  FastAPI app/api/leads.py, миграция 0005_consent_leads: consents, lead_drafts,
  lead_submissions, audit_events. Новых зависимостей/сервисов нет.
- Consent decisions append-only: цель, текст/версия/получатель, grant/decline/withdraw,
  revision, given_at/withdrawn_at/recorded_at. Нет API удаления истории.
- assistant обязателен для новых сообщений/PATCH/confirm, проверяется до inference
  и повторно под блокировкой. Чтение истории и базовые инструменты доступны.
  Существующие API-клиенты должны явно предоставить assistant перед записью.
- marketing необязателен; отказ не блокирует гео/финансы/каталог/запрошенный подбор/lead.
  Рассылки не реализованы. demo_lead — отдельная цель подготовки и mock-отправки.
- Draft хранит подтверждённый профиль/версию отдельно от минимального payload:
  city/category, optional budget/funding/format; выбранные ProductView, источники,
  fingerprint каталога, происхождение правок. Нет паспорта, контактов, истории,
  токенов, OSM-score или синтетических финансовых показателей в payload.
- Правки draft увеличивают revision и снимают confirm. Изменение профиля/решения
  согласия требует явного обновления и нового подтверждения. Каталог повторно
  проверяется перед действием; неизвестные/просроченные продукты блокируются.
- Гостевая изоляция и общая блокировка conversation с profile updates/revocation.
  Submit атомарно сохраняет receipt + submitted + audit. UUID idempotency_key,
  UNIQUE(session,key)/draft предотвращают дубли. Точный повтор возвращает прежнюю
  квитанцию; конфликт/отзыв/stale запрещают новый POST. GET истории остаётся.
- MockLeadAdapter не имеет HTTP-транспорта, банковского URL или внешнего номера.
  Receipt: demo_created, sent_to_bank=false и строго:
  «Демонстрационная заявка создана. Данные в ВТБ не отправлены».
- React LeadFlow после каталога: выбор, редактирование/исключение полей, согласия,
  точный JSON-preview, два явных подтверждения, receipt/history/reload, ошибки/mobile.
  Перед первым сообщением assistant consent раскрывается в чате. После отзыва
  автоматического regrant нет; управление — в разделе продуктов.
- README, CONSENT_LEADS.md, CONVERSATION_API.md, USER_INTERFACE.md, ADR-0008.
  eval_local_llm.py адаптирован: обязательный --consent-to-local-evaluation
  разрешает только встроенные вымышленные сценарии, без marketing/lead.

## Проверки

- pytest apps/api/tests/test_leads.py -q: 10 PASS; strict validation/confirmation,
  fingerprint/revision/stale, mock receipt с запрещёнными socket-соединениями.
- PostgreSQL полный прогон: 55 PASS, 1 FAIL в новой финансовой фикстуре (не коде).
  Исправлены обязательная sensitivity_changes и целые sales_per_day.
  Повтор целевого tests/integration/test_leads.py: 6 PASS. Все остальные 50 тестов
  прошли полный прогон; GitHub Compose CI выполняет полный набор 56 заново.
  В том числе чужие ID, отсутствие/отзыв согласий, маркетинг не блокирует финансы,
  stale профиль, изменения/дубли, concurrent submit/edit, отзыв во время inference,
  истечение каталога, аудит, миграция/check/rollback без потери существующих данных.
- npm --prefix apps/web test: 26 PASS (5 новых LeadFlow).
- npm --prefix apps/web run test:e2e: 3 mock Chromium PASS, включая lead preview,
  отдельное согласие, исключение бюджета, confirm, receipt/reload/mobile.
- prek run --all-files: Ruff/format/mypy/pytest/ESLint/TypeScript/Vitest PASS.
  Production build/Compose build PASS; прежний MapLibre large-chunk warning.
- Compose db/api/web healthy, миграция 0005 применена, HTTP smoke PASS.
  Данные PostGIS/volumes сохранены, системные настройки не менялись.
- Настоящий BA010_REAL=1 + BA010_ARTIFACT_DIR=test-results/ba012-regression:
  Qwen → confirmed profile → настоящие зоны/рейтинг → finance/recalculation →
  каталог → отказ от marketing → выбор РКО/торгового эквайринга → отдельный consent →
  preview/confirm → mock receipt → reload: PASS. Console/page errors отсутствуют.
  Артефакты docs/screenshots/BA-012-*.png и BA-012-verification.json без ключей.
  Qwen qwen3:4b-instruct-2507-q4_K_M, новых моделей не скачивали.
- eval-скрипт: --help и Ruff PASS; полный BA-005 eval заново не выполнялся.
  Реальная LLM проверена отдельным полным browser E2E; mock не выдан за LLM.

## Ограничения и следующие действия

1. Проверить PR/CI BA-012; merge только по решению владельца.
2. Тексты демонстрационные, не юридические документы ВТБ. До пилота legal/privacy/
   retention/access review и согласованная реальная интеграция. BA-020 не реализована.
3. Каталог BA-011 остаётся demonstration/unconfirmed/cached_only, без проверенных
   актуальных условий. Выбор — интерес, не банковское одобрение. Нет кредитного score.
4. Audit — принятые действия приложения, не WORM и не отдельный журнал отказов.
   Нет аккаунтов/восстановления гостевого ключа, автоматической PII-редакции,
   неограниченно масштабируемого архива, банковского API и отправки контактов.
5. BA-013 (пешеходный catchment) — только после отдельного разрешения.
