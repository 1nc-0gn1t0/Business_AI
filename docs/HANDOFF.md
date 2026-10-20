# Business AI — HANDOFF

## Состояние на 20.10.2026

- Фаза F0. BA-002 завершена: CI и проверки реализованы, локально и в GitHub Actions PASS.
- Ветка для продолжения после интеграции: main. Источники реализации: feat/BA-001-project-skeleton (aa78db6) и feat/BA-002-ci; BA-001 является предком BA-002.
- Последовательная интеграция: BA-001 → main через https://github.com/1nc-0gn1t0/Business_AI/pull/1 (merge c0dba59), затем BA-002 → main через https://github.com/1nc-0gn1t0/Business_AI/pull/2. Используются merge commits с сохранением истории, без force push и удаления веток.
- Реализация CI: 96c2e62, исправление action-тега: 7b37866; оба коммита отправлены в origin/feat/BA-002-ci. Фактический HEAD после обновления HANDOFF указан в итоговом сообщении.
- Владелец разрешил последовательное слияние PR #1 и #2 после проверки изменений и CI. BA-003 не начиналась и требует отдельного разрешения.

## Сделано в BA-002

- .github/workflows/ci.yml: push во все ветки, PR в main, ручной запуск; contents: read, отмена устаревших запусков, таймауты.
- Checks на Ubuntu и Windows: Python 3.12, Node.js 24, uv 0.13.1, prek 0.5.4; установка из lock-файлов, Ruff lint/format, строгий mypy (API и тесты), pytest, ESLint TypeScript/React Hooks, tsc и Vite build.
- Проверка соответствия apps/api/requirements.txt экспорту uv.lock, чтобы Docker не использовал устаревшие зависимости.
- Compose smoke на Ubuntu: сборка трёх контейнеров, ожидание healthcheck, scripts/smoke.ps1 с реальным PostGIS. При сбое — диагностика; очистка тестовых контейнеров/volume выполняется всегда.
- prek.toml содержит те же lint/typecheck/unit checks; hook установлен в текущем клоне через prek install. Другие клоны устанавливают hook отдельно по README.
- Добавлены mypy и ESLint-зависимости, обновлены lock-файлы, аннотации двух существующих тестов, исключения .mypy_cache. Архитектура и бизнес-логика не менялись.
- README описывает CI, локальные команды и установку hook. Полный список файлов — git diff aa78db6...HEAD.

## Проверки BA-002

Из корня репозитория, если не указано иное. Доступ к зависимостям/локальному обмену разрешался вне песочницы.

- uv sync --locked --project apps/api: PASS.
- uv tool run --from prek==0.5.4 prek run --all-files: PASS, все 6 hooks (Ruff lint, Ruff format, mypy, pytest, ESLint, TypeScript).
- mypy: PASS, 5 файлов; pytest: 2 существующих теста (200 с PostGIS и 503 без утечки реквизитов).
- npm --prefix apps/web run lint: PASS, без предупреждений ESLint.
- npm --prefix apps/web run build: PASS, tsc и Vite.
- В apps/api: uv export --no-dev --no-hashes --no-emit-project --format requirements-txt --output-file requirements.txt; git diff --exit-code -- requirements.txt: PASS.
- docker compose config --quiet: PASS.
- GitHub Actions для 7b37866: PASS, Checks (ubuntu-latest), Checks (windows-latest), Compose smoke. Запуск: https://github.com/1nc-0gn1t0/Business_AI/actions/runs/39182945060. Установка из lock, экспорт requirements, все prek checks, сборка frontend и реальный Compose smoke прошли на чистых runners.
- Исправлена обнаруженная CI-ошибка: major-тег setup-uv@v10 отсутствовал; используется опубликованный точный тег v10.3.0. После исправления все jobs прошли.

## Сохранившийся результат BA-001

React → FastAPI /healthz → PostgreSQL 17/PostGIS 3.5; Compose, lock-файлы и Windows/WSL2 инструкции. Проверены чистый клон с новой БД, smoke, пространственный запрос, отказ/восстановление БД и браузерные статусы. Коммиты f2ffb4b, 3bc62e5, aa78db6 отправлены в origin/feat/BA-001-project-skeleton.

Запуск: docker compose up --build. Веб http://localhost:5173; readiness http://localhost:8000/healthz; OpenAPI http://localhost:8000/docs. Smoke: powershell -NoProfile -File scripts/smoke.ps1. Остановка с сохранением данных: docker compose down.

## Ограничения и следующий шаг

- Локальное окружение разработки, демонстрационные реквизиты БД; внешние API/секреты не нужны.
- Бизнес-модули, AI-диалог, аналитика, карта и банковские интеграции ещё не реализованы.
- CI не включает настройки branch protection: их определяет владелец репозитория.
- Блокеров BA-002 нет. Перед новой задачей синхронизировать main через git pull --ff-only и проверить актуальный CI main. Фактические merge SHA и итоговый CI приведены в отчёте интеграции; состояние PR доступно по ссылкам выше.
- Только с разрешения владельца BA-003: доменные DTO, миграции и provenance enum.
