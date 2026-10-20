# Business AI — HANDOFF

## Состояние на 20.10.2026

- Фаза F0, задача BA-003: DTO, ORM и миграции реализованы; локальные проверки PASS, интеграционный CI пока ожидается.
- Ветка feat/BA-003-data-contracts создана от синхронизированного main/origin/main dad73d7, рабочее дерево перед началом было чистым.
- BA-001 и BA-002 ранее интегрированы последовательно через PR #1 и #2. Их история сохранена.
- BA-003 требует review: push/PR и CI будут подтверждены в итоговом сообщении. Самостоятельный merge запрещён.
- BA-004 не начиналась, требуется отдельное разрешение владельца.

## Что сделано в BA-003

- app/api/schemas.py: BusinessProfile, BusinessPreferences, MetricWithProvenance, AnalysisRun. Неизвестные поля запрещены, поля DTO frozen; денежные значения Decimal, даты с timezone, конечные значения метрик.
- app/domain/enums.py: DataOrigin из шести значений, Confidence, Funding, ConfirmationState. Origin/источник/версия/даты/confidence/limitations у метрики обязательны; synthetic требует явных ограничений и confidence=not_applicable.
- app/db/models.py: SQLAlchemy-модели business_profiles, analysis_runs, location_metrics. Native PostgreSQL enums, NOT NULL/CHECK/FK, индекс анализа, JSONB снимков/предпочтений, Numeric бюджета.
- Alembic 0001_contracts: воспроизводимый upgrade/downgrade и PostGIS. Credentials через libpq PG*, без секретов в URL/ini. PostGIS сохраняется при downgrade и исключён из autogenerate удаления.
- Compose запускает migrate до API; Dockerfile имеет отдельную test-стадию. Профиль test создаёт временные БД для интеграционных тестов, не откатывая БД приложения.
- CI Compose smoke запускает интеграционные тесты; mypy/prek проверяет также миграции. Зависимости и lock/requirements обновлены вместе.
- docs/DATA_CONTRACTS.md описывает контракты, ограничения, команды миграций и тестов; README актуализирован.
- HTTP endpoints диалога/аналитики, LLM и геосервисы не добавлены. Проверка FastAPI 422 выполняется тестовым маршрутом, без создания фиктивного product API.

## Проверки

- pytest apps/api/tests: 43 passed, 20 skipped (интеграционные тесты требуют отдельный test-профиль).
- uv tool run --from prek==0.5.4 prek run --all-files: PASS, все 6 hooks (Ruff lint/format, mypy, pytest, ESLint, TypeScript).
- mypy API/тестов/миграций: PASS, 14 файлов.
- Alembic upgrade head --sql: PASS, SQL генерируется без подключения к БД.
- docker compose config --quiet: PASS.
- Локальные Docker smoke/DB-тесты пока не запускались успешно: Docker Desktop установлен, но Engine не ответил после попыток запуска. Системные настройки не менялись. Интеграционные проверки должны быть подтверждены в GitHub CI.

## Запуск

- docker compose up --build: DB → migrate → API → web.
- http://localhost:5173; http://localhost:8000/healthz; http://localhost:8000/docs.
- docker compose run --rm migrate alembic current (или check).
- docker compose --profile test run --build --rm db-tests: PostgreSQL-тесты во временных БД ba003_test_*.
- Для локальных Python-команд и настроек PG* см. docs/DATA_CONTRACTS.md. Не запускать downgrade основной БД ради теста.

## Границы и следующий шаг

- Пока provenance хранится в самой метрике; справочник SourceRecord и геотаблицы относятся к будущим провайдерам/геоданным. UUID conversation_id/candidate_id пока без FK к ещё не существующим таблицам; FK метрики к AnalysisRun уже обязателен.
- Подтверждение профиля не означает готовность анализа; полнота и multi-turn логика — BA-004.
- Следующий шаг сейчас: проверить интеграционный CI, исправить ошибки, создать PR BA-003 → main и оставить его на review без merge.
- После принятия BA-003 только по разрешению владельца — BA-004: conversation state и extract profile.
