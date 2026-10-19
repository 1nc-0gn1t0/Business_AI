# Business AI — HANDOFF

## Состояние на 19.10.2026

- Фаза F0. Текущая задача BA-002: CI и проверки реализованы; локально PASS, запуск в GitHub Actions ещё ожидается.
- Ветка: feat/BA-002-ci. main синхронизирован с origin/main (62b2ba4) и не изменялся.
- В main ещё нет BA-001. Ветка BA-002 включает завершённую BA-001 (aa78db6) через fast-forward только feature-ветки. При review учитывать эту зависимость.
- Фактический HEAD, результат push и ссылка на CI будут указаны в итоговом сообщении и дополнены здесь после проверки.
- BA-003 не начиналась. Слияние с main запрещено до проверки владельцем.

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
- GitHub Actions: ещё не проверено. До успешного запуска критерий приёмки BA-002 не считается подтверждённым.

## Сохранившийся результат BA-001

React → FastAPI /healthz → PostgreSQL 17/PostGIS 3.5; Compose, lock-файлы и Windows/WSL2 инструкции. Проверены чистый клон с новой БД, smoke, пространственный запрос, отказ/восстановление БД и браузерные статусы. Коммиты f2ffb4b, 3bc62e5, aa78db6 отправлены в origin/feat/BA-001-project-skeleton.

Запуск: docker compose up --build. Веб http://localhost:5173; readiness http://localhost:8000/healthz; OpenAPI http://localhost:8000/docs. Smoke: powershell -NoProfile -File scripts/smoke.ps1. Остановка с сохранением данных: docker compose down.

## Ограничения и следующий шаг

- Локальное окружение разработки, демонстрационные реквизиты БД; внешние API/секреты не нужны.
- Бизнес-модули, AI-диалог, аналитика, карта и банковские интеграции ещё не реализованы.
- CI не включает настройки branch protection: их определяет владелец репозитория.
- Следующий шаг сейчас: дождаться Actions для BA-002, исправить возможные ошибки, записать фактические результаты и подтвердить push.
- После завершения BA-002 — review владельца. Только с его разрешения BA-003: доменные DTO, миграции и provenance enum.
