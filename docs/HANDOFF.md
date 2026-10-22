# Business AI — HANDOFF

## Состояние на 22.10.2026

- BA-001…BA-004 объединены в main. Перед BA-005 main синхронизирован с origin/main
  на 4b946e5 (merge PR #4), рабочее дерево было чистым.
- BA-005 реализована в codex/BA-005-local-llm от этого main. Коммит/PR и GitHub CI
  после push — в итоговом сообщении. Самостоятельный merge запрещён.
- BA-006 не начиналась; требуется отдельный запрос владельца.

## BA-005: сделано

- app/adapters/llm.py: сменный DialogueLLM protocol, реальный OllamaLLM и явный
  deterministic StubLLM. URL/модель/таймаут/контекст настраиваются окружением.
  Без платных API, cloud fallback, обучения и новых Python-зависимостей.
- Реально загружена одна qwen3:4b-instruct-2507-q4_K_M: 4.02B, Q4_K_M,
  Apache 2.0, около 2.5 GB весов. Ollama 0.40.8 в business-ai-ollama;
  веса в business-ai_ollama_data, вне Git.
- Вход модели: компактный профиль, последний вопрос, текущее сообщение.
  JSON Schema разрешает только extract_business_profile: изменения с цитатами,
  неоднозначность и намерение. Реальные изменения требуют цитаты текущего ввода,
  неизменившиеся повторы игнорируются. ProfilePatch/BusinessProfile валидирует сервер.
- Извлечение города, категории, бюджета RUB, формата, финансирования. Вопросы/summary
  из разрешённых шаблонов. Произвольный текст модели не выдаётся за аналитику/цены/ВТБ.
  Аналитические инструменты BA-006 и далее не реализованы.
- Сохранены API BA-004, auth, expected_version, подтверждение/снятие подтверждения,
  сообщения и история. Inference без row lock, перед записью версия проверяется
  повторно под FOR UPDATE. Ошибки модели не пишут частичное состояние.
- 503 llm_unavailable/llm_configuration_error, 504 llm_timeout,
  502 llm_invalid_response; trace_id без сырых данных, лимиты ответа и retry/backoff.
- Миграция 0003_llm_mode добавляет extraction_mode (rules/stub/ollama), старые
  строки получают rules. GET возвращает сохранённый ответ/уточнение.
- README: Windows Ollama и GPU-контейнер совместно с Compose. ADR-0002,
  CONVERSATION_API, локальные LLM-разделы PROJECT_PLAN/PROJECT_CONTEXT обновлены.

## Проверки

- pytest apps/api/tests -q: 92 passed, 31 skipped (БД отдельно).
- Unit-тесты: mock HTTP, schema/value/JSON errors, timeout, unavailable, retry,
  whitelist, evidence, повторы профиля, неоднозначность и явный stub.
- docker compose --profile test run --build --rm db-tests: 31 passed,
  реальные PostgreSQL/PostGIS, миграции, auth, сохранение mock-LLM результата,
  rollback и конкурентная правка во время inference. Профиль явно stub: CI без GPU/весов.
- prek run --all-files: PASS; Ruff lint/format, strict
  mypy, pytest, ESLint, TypeScript. npm --prefix apps/web run build: PASS.
- Compose build/start и HTTP smoke: PASS; db/api/web healthy, migrate Exited(0).
- Настоящий Ollama eval: 10/10 шагов PASS. Обязательная кофейня/Казань/2 млн,
  уточнения, подтверждение, Самара/3 млн, неоднозначность, валюта, аналитика, injection.
  Чтением проверены профиль/история/сообщения. Тёплые LLM-шаги 1.45–8.39 s,
  подтверждение сервером без inference 0.016 s.
- Повторная холодная загрузка после выгрузки: HTTP 200 за 37.5 s.
  Самый первый запуск дал 504 при старом лимите 90 s, лимит увеличен до 120 s.
- RTX 3050 Ti 4 GB: ollama ps 18% CPU / 82% GPU, около 2.9 GB;
  nvidia-smi около 2340 MiB, Ollama-контейнер около 3.2 GiB RAM.
- Детали/ошибки ранних прогонов: LLM_EVALUATION.md и evals/BA-005-local.json.
  Это реальная модель, отдельно от mock-тестов. scripts/eval_local_llm.py воспроизводит eval.
- Docker/localhost доступны вне песочницы. Системные настройки не менялись;
  существующие volumes не удалялись. Eval создаёт анонимные беседы в БД приложения.

## Ограничения и продолжение

- Малый целевой eval не доказывает общее качество. В ранних прогонах были пропуски,
  лишние факты и неверная неоднозначность: исправлены контракт/контекст, ошибки
  описаны в LLM_EVALUATION. Смысловые ошибки всё ещё возможны: проверять профиль,
  точные правки делать PATCH. Полный GPU offload не достигнут.
- Списки районов/ограничений — через PATCH; LLM извлекает пять основных полей.
  История не отправляется целиком. Frontend-чат остаётся BA-010.
- Запуск: docker start business-ai-ollama; docker compose up --build --detach --wait.
  При остановленном Ollama сообщения дают 503, PATCH остаётся доступным.
- Следующий шаг: review PR BA-005 владельцем, без автоматического merge.
  Только после разрешения — BA-006 (OSM ingest/PostGIS POI).
