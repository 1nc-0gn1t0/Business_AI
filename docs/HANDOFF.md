# Business AI — HANDOFF

## Состояние на 19.10.2026

- Фаза: F0 — основание проекта.
- Задача: BA-001 завершена — технический скелет реализован и проверен из чистого клона.
- Ветка: feat/BA-001-project-skeleton.
- Коммит реализации: f2ffb4b (база: 62b2ba4). Фактический HEAD после обновления HANDOFF указан в итоговом сообщении.
- Push подтверждён 19.10.2026: git push --set-upstream origin feat/BA-001-project-skeleton завершился успешно (Everything up-to-date); удалённая ветка содержит коммит 3bc62e5 и реализацию f2ffb4b. Блокер авторизации снят. Фактический HEAD после этого уточнения и результат его отправки указаны в итоговом сообщении.
- Бизнес-модули, AI-диалог, карта, аналитика и банковская интеграция ещё не реализованы.

## Что сделано

- Compose: PostgreSQL 17/PostGIS 3.5 с постоянным volume, FastAPI и собранный React/TypeScript через nginx.
- Зависимости запускаются по healthcheck; HTTP-порты доступны только с локального компьютера, порт БД не опубликован.
- GET /healthz выполняет SELECT PostGIS_Version(); возвращает 200 с версией либо 503 без реквизитов подключения.
- React показывает доступность API/БД через same-origin nginx proxy, состояние ожидания и ошибку.
- Созданы apps/api, apps/web, infra/docker, scripts, data/synthetic и docs/adr.
- Добавлены lock-файлы, Dockerfiles, .dockerignore, .gitignore, .env.example, инструкции Windows/WSL2, smoke.ps1.
- Добавлены два API-теста и минимальные локальные prek hooks: Ruff lint/format и TypeScript. Полный CI относится к BA-002 и не начинался.
- Архитектура соответствует PROJECT_PLAN; новых архитектурных решений нет. Данные и секреты внешних сервисов не нужны.

## Проверки

Все команды выполнялись из корня, если не указано иное. Проверки с доступом к Docker, TestClient и Vite запускались вне песочницы: внутри неё были ограничения доступа/локального обмена.

- uv run --locked --project apps/api pytest apps/api/tests: PASS, 2 теста (200 с PostGIS и 503 без раскрытия реквизитов), без предупреждений.
- npm --prefix apps/web run build: PASS, TypeScript и production Vite build. Сборка также прошла внутри Docker.
- prek run --all-files: PASS, API lint, API formatting, Web TypeScript.
- docker compose config --quiet: PASS.
- docker compose up --build --detach --wait --wait-timeout 180: PASS, три сервиса healthy, новый volume без .env.
- powershell -NoProfile -File scripts/smoke.ps1: PASS, API напрямую, API через nginx и собранная React-страница.
- Чистый локальный клон коммита f2ffb4b, без .env, node_modules/.venv и старой БД: docker compose -p business-ai-ba001-clean up --build --detach --wait --wait-timeout 180 (из клона, с API_PORT=18000 и WEB_PORT=15173): PASS, три сервиса healthy. scripts/smoke.ps1 на этих портах: PASS. Временные контейнеры и отдельный volume удалены после проверки; основное окружение сохранено.
- docker compose exec -T db psql -U business_ai -d business_ai -c "SELECT PostGIS_Version(), ST_AsText(ST_SetSRID(ST_MakePoint(49.1,55.8),4326));": PASS, PostGIS 3.5 и POINT(49.1 55.8). Это проверка геометрии, а не бизнес-данные.
- Реальная остановка db: /healthz вернул 503; после docker compose up --detach --wait --wait-timeout 90 smoke снова PASS.
- Playwright: страница отображает успешный статус и версию БД, штатная консоль без ошибок/предупреждений. При подставленном HTTP 503 показывает ошибку; после снятия подстановки и reload — успешный статус.

## Запуск и ограничения

Из корня: docker compose up --build. Веб: http://localhost:5173; API: http://localhost:8000/healthz; OpenAPI: http://localhost:8000/docs.
Остановка с сохранением данных: docker compose down. Детали, зависимости и нестандартные порты — в README.

Это локальное окружение разработки. Демонстрационный пароль из Compose/.env.example нельзя использовать в production. Изменение POSTGRES_* не меняет уже инициализированный volume.
Нет утверждённого первого города/отрасли, партнёрских данных и доступа к API ВТБ/LLM. Для BA-001 это не блокеры. Доменных DTO и миграций пока нет (BA-003); расширение PostGIS создаётся штатным образом postgis/postgis.

## Следующий шаг — только по разрешению владельца

BA-002: GitHub CI, согласованные линтеры/типизация/тесты и prek. Критерий: проверки проходят в GitHub CI на чистом клоне.
Затем BA-003: доменные DTO, миграции, provenance enum. Не показывать аналитику до обязательной маркировки происхождения данных.
BA-002/BA-003 в этом сеансе не начинались.
