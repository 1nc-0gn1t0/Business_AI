# Business AI — HANDOFF

## Состояние на 20.10.2026

- BA-003 объединена в main через PR #3 (merge d1962ed), подтверждено GitHub API.
- BA-004 реализована в feat/BA-004-conversation-state от синхронизированного чистого main d1962ed. Локальные проверки PASS; интеграционный CI ещё ожидается.
- Самостоятельное слияние запрещено. Ссылка на PR, фактический HEAD и push будут подтверждены в итоговом сообщении.
- BA-005 не начиналась, требуется отдельное разрешение владельца.

## Сделано в BA-004

- FastAPI /api/v1/conversations: создание и чтение беседы/профиля, сообщения, частичный PATCH, явное подтверждение, пагинированные сообщения и история снимков.
- Состояния collecting → awaiting_confirmation → confirmed. Основные вводные: категория, город, положительный общий бюджет RUB, формат и финансирование. Правка снимает подтверждение; пустая правка сохраняет его. Null очищает поля, вложенный PATCH сохраняет неуказанные предпочтения.
- extract_business_profile — ограниченные локальные правила русского ввода, явно extraction_mode=rules. Для произвольных названий есть метки город:/бизнес:/формат: и typed PATCH. LLM, tool calling, геоаналитика, финрасчёты и банковская отправка не добавлены.
- conversations/messages/profile_revisions сохраняются в PostgreSQL. expected_version и SELECT FOR UPDATE защищают от потери параллельных правок. Профиль, ответы, история и состояние пишутся одной транзакцией с commit до успешного HTTP-ответа.
- Гостевая беседа защищена случайным токеном X-Conversation-Token; в БД только SHA-256, сам токен выдаётся один раз. 401 без токена, одинаковый 404 для неизвестной беседы/чужого токена. Ошибки SQL и секреты не выводятся.
- Alembic 0002_conversations добавляет таблицы и FK business_profiles.conversation_id. Старые профили сохраняются как legacy_import без выдачи нового публичного доступа; downgrade сохраняет business_profiles.
- nginx/Vite проксируют /api/. Отдельный frontend-чат остаётся BA-010.
- Решения: docs/adr/ADR-0001-conversation-state.md. API/PowerShell-пример/границы: docs/CONVERSATION_API.md. README и DATA_CONTRACTS актуализированы.

## Проверки

- pytest apps/api/tests -q: 66 passed, 26 skipped (PostgreSQL tests выполняются отдельным test-профилем).
- uv tool run --from prek==0.5.4 prek run --all-files: PASS, Ruff lint/format, строгий mypy, pytest, ESLint и TypeScript.
- npm --prefix apps/web run build: PASS, tsc и Vite.
- Интеграционные тесты: добавлены реальные HTTP multi-turn, подтверждение/снятие подтверждения, auth/изоляция, история/пагинация, rollback, конкурентные и устаревшие правки, новый FK и сохранность legacy-профилей при upgrade/downgrade. Общие фикстуры вынесены для использования во временных БД.
- Локальный Docker Engine недоступен (pipe отсутствует). Новые PostgreSQL-сценарии должны быть подтверждены в GitHub CI; системные настройки не менялись.

## Запуск и продолжение

- docker compose up --build: DB → migrate → API → web. OpenAPI http://localhost:8000/docs, web http://localhost:5173.
- docker compose --profile test run --build --rm db-tests: DB/API tests в отдельных временных БД; БД приложения не откатывается.
- Пример работы с токеном, версией и исправлениями — docs/CONVERSATION_API.md. Потерянный гостевой токен публичным API не восстанавливается.
- Следующий шаг сейчас: проверить CI, исправить ошибки, открыть PR BA-004 → main и оставить на review без merge.
- После принятия BA-004 только по разрешению владельца — BA-005: LLM adapter и deterministic stub. Не выдавать текущие правила за подключённую модель.
