# BA-012: согласия и локальная демонстрационная заявка

**Данные в ВТБ не отправляются.** Нет банковского HTTP-клиента, CRM, внешнего номера
заявки или кредитного решения. Тексты — демонстрационные тексты Business AI,
не утверждённые документы ВТБ. До пилота необходимы правовая проверка, retention policy,
договоры и согласованная инфраструктура (BA-020).

## Согласия

| Цель | Версия | Что разрешает |
|---|---|---|
| assistant | assistant-demo-v1 | Новые сообщения, изменение и подтверждение профиля |
| marketing | marketing-demo-v1 | Отдельная необязательная цель; рассылки не реализованы |
| demo_lead | demo-lead-v1 | Подготовка, изменение, подтверждение и локальная mock-отправка |

В чате раскройте «Использование ассистента» и отметьте отдельное согласие до первого
сообщения. Сервер проверяет его до inference и повторно под блокировкой перед записью.
Это дополнительное условие записи к API BA-004, включая существующие сессии;
формат запросов сохранён. После отзыва автоматического повторного предоставления нет:
явное согласие заново предоставляется в разделе продуктов.

Отказ/отзыв marketing не блокирует геоаналитику, финансы, каталог, подбор по запросу
и mock-заявку. Запрошенный пользователем информационный подбор отделён от рассылок.
Отзыв assistant блокирует новые записи чата/профиля, но не чтение истории/квитанций
и базовые расчёты. Отзыв demo_lead блокирует новые действия заявки.

Каждое решение — новая строка `consents`: session, purpose, revision, text_version,
status, given_at, withdrawn_at, recorded_at. Статусы: not_given (виртуальный, до решения),
granted, declined, withdrawn. Старые решения сохраняются; API удаления нет.
Каждое решение также сохраняет снимок текста с версией и получателем.
Версии текстов в `app/leads/policy.py` нельзя переиспользовать после изменения смысла.
Новая версия требует нового согласия. `expected_revision` защищает от гонок.

## Состав и редактирование

Обязательны город и тип бизнеса (непустые строки, максимум 100 символов).
Необязательны бюджет (Decimal ≥ 0, два знака), источник средств (enum), формат.
Пустое значение в редакторе исключает значение: в типизированном JSON будет `null`.
Payload также содержит выбранные ProductView с версиями/источниками/ограничениями,
версию/fingerprint каталога, mode=demonstration, recipient=local_mock_only и
происхождение полей confirmed_profile/draft_user_input.

Паспорт, телефон, ФИО, email, переписка, токен, OSM-score и финансовые допущения
не входят в payload. Дополнительные поля отклоняются. Не вводите реальные персональные
данные в свободные поля: автоматической PII-классификации нет.
Полный подтверждённый профиль хранится **внутренним снимком**, отдельно от payload.
Правки заявки не меняют профиль чата; их источник явно отмечен в предпросмотре JSON.

Выбор продукта означает интерес пользователя, не соответствие условиям банка.
Можно явно выбрать доступную demo-карточку, даже если matcher просит уточнения.
Неизвестные/просроченные/заблокированные продукты отклоняются. Каталог проверяется
при подготовке, подтверждении и submit. Действующие условия BA-011 по-прежнему
не подтверждены; демонстрационные карточки не становятся действующими предложениями.

## Состояния и защита

`draft → confirmed → submitted`. PUT увеличивает revision и снимает подтверждение.
После submit редактирование запрещено, для следующей заявки нужен новый черновик.
Черновик фиксирует профиль/версию, payload/fingerprint, конкретные решения согласия.
Смена версии профиля делает его stale. Нужно подтвердить профиль, явно обновить поля,
сохранить черновик и заново подтвердить состав. После отзыва и повторного предоставления
согласия также требуется обновление и подтверждение. Несохранённые правки блокируют UI.

Все операции защищены X-Conversation-Token и общей с записью профиля блокировкой
строки conversations. В одной транзакции проверяются владелец, профиль, согласия,
каталог, ревизия и fingerprint; сохраняются submission, submitted и AuditEvent.
Отзыв/изменение, зафиксированные раньше submit, не игнорируются. Inference не держит
блокировку. LLM не участвует в разрешении операции, сетевого вызова банка нет.

POST submit требует UUID idempotency_key. Точный повтор возвращает прежнюю квитанцию,
без новой операции/аудита. Иной payload/черновик с тем же ключом или новый ключ для
отправленного черновика → 409. Уникальны (session, key) и draft_id.
Повторы также проверяют текущие профиль/согласия/каталог: после отзыва POST запрещён,
но GET квитанции доступен. При потере ответа UI сохраняет ключ для повтора;
после reload читает сохранённые квитанции.

AuditEvent фиксирует принятые решения согласия, создание/обновление/подтверждение
черновика и mock-submission: actor=guest_session, action, object_id, timestamp, outcome.
Нет токенов/значений полей. Отказы откатывают транзакцию и возвращают код; отдельного
журнала неуспешных попыток нет. Consent/submission/audit не имеют API изменения/удаления,
FK без каскадного удаления. Это аудит приложения, не WORM или защита от DB-admin.

## API

Публичный `GET /api/v1/consent-texts` возвращает текущие тексты/версии.
Остальные пути относительно `/api/v1/conversations/{id}`, требуют гостевой ключ:

| Метод | Путь | Тело / результат |
|---|---|---|
| GET | /consents | Тексты и текущие решения всех целей |
| PUT | /consents/{purpose} | expected_revision, text_version, decision=grant/decline/withdraw |
| GET | /leads | Свои черновики со stale-флагом и квитанции |
| POST | /leads/drafts | expected_profile_version, catalogue_fingerprint, product_ids, fields → 201 |
| GET | /leads/drafts/{draft_id} | Состав, происхождение, версии и статус |
| PUT | /leads/drafts/{draft_id} | То же, плюс expected_revision; явное обновление |
| POST | /leads/drafts/{draft_id}/confirm | expected_revision, payload_fingerprint, confirmed=true |
| POST | /leads/drafts/{draft_id}/submit | То же, плюс idempotency_key → LeadReceipt |
| GET | /audit?offset=0&limit=50 | Свои метаданные аудита; limit ≤ 100 |

401 без ключа; 404 чужая/отсутствующая сессия или заявка; 422 валидация;
403 consent_required_assistant/demo_lead. Конфликты 409: consent_revision_conflict,
consent_text_changed, lead_revision_conflict, lead_payload_conflict, lead_profile_stale,
lead_consent_changed, lead_confirmation_required, lead_already_submitted,
lead_idempotency_conflict, lead_product_unavailable, bank_catalogue_version_conflict.
503 bank_catalogue_unavailable. Полные DTO — OpenAPI.

Квитанция содержит локальные id/draft_id, draft_revision, profile_version,
payload/fingerprint, версии согласий, created_at, status=demo_created,
sent_to_bank=false и строго:

> Демонстрационная заявка создана. Данные в ВТБ не отправлены

UUID — внутренний идентификатор Business AI, не номер банка.

## Запуск и проверки

`docker compose up --build --detach --wait --wait-timeout 180` применяет
миграцию `0005_consent_leads`. Volumes/данные не удалять. Новых зависимостей/сервисов нет.
LeadAdapter — Protocol, единственная реализация MockLeadAdapter без транспорта.
Замена требует согласованного банковского пилота, не настройки bank URL в демо.

Unit: `uv run --locked --project apps/api pytest apps/api/tests/test_leads.py -q`.
PostgreSQL: `docker compose --profile test run --build --rm db-tests`.
UI: `npm --prefix apps/web test`; mock Chromium: `npm --prefix apps/web run test:e2e`.
Автотесты без GPU, Qwen и банка; PostgreSQL тесты в изолированных временных БД.
Unit-проверка adapter запрещает socket-соединения.

Для настоящего Qwen/PostGIS-сценария задайте BA010_REAL=1,
BA010_ARTIFACT_DIR=test-results/ba012-regression и запустите test:e2e.
Route mocks не регистрируются: Qwen → профиль → зоны/рейтинг → финансы → каталог →
отказ от marketing → отдельное согласие → preview → confirm → receipt → reload.
Снимки `screenshots/BA-012-*.png`, `BA-012-verification.json` не содержат гостевых ключей.
Traces/HAR/video отключены. Фактические результаты — в HANDOFF.
