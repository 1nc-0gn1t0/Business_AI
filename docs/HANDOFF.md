# Business AI — HANDOFF

## Состояние на 23.10.2026

- PR #8 BA-008 объединён, merge `486018b1497b8fc94dcc410941e16950e8abc2b1`.
  Перед BA-009 main синхронизирован с origin/main, рабочее дерево было чистым.
- BA-009 реализована в `codex/BA-009-financial-engine` от `486018b`.
  Фактический HEAD, PR и статус GitHub CI после push — в итоговом сообщении.
  Не объединять автоматически. BA-010 не начиналась.
- LLM/диалоги и геомодули BA-003…BA-008 сохранены; миграций/зависимостей не добавлено.

## Сделано в BA-009

- `app/finance/schemas.py`, `engine.py`; `app/api/finance.py`, route
  POST `/api/v1/finance/calculate` и подключение router в main.py.
- Чистый Decimal-движок: отдельный Context(prec=64, HALF_UP), без float,
  независим от внешнего precision/rounding/traps. Новые money/ratio inputs —
  decimal strings/integers; float/bool отклоняются. Вычисленные деньги/counts — строки.
- Стартовая потребность: оборудование, ремонт, депозит, запас, организационные,
  прочие расходы и резерв. Это использования денег, не всё является expense/CAPEX.
  Сравнение с budget BusinessProfile: остаток/дефицит либо budget_unknown.
- Месячные fixed/variable costs, revenue, точная/display unit margin,
  monthly contribution, operating result, ceil BE по неокруглённой марже.
  Variable costs округляются за месяц до копеек перед вычитанием; строки сходятся.
- Три явно заданных сценария; optional полный override fixed costs сценария,
  сравнение с base, one-at-a-time sensitivity чека/продаж/аренды/ratio.
  Выход perturbation за домен → outside_domain/null, без скрытого clamp.
- У каждой существенной вводной origin/source/version/confidence/limitations.
  Документированные факты требуют caller attestation + evidence_ref/date;
  это не независимая проверка документа сервисом. Демо-вводные только synthetic,
  бюджет user_input, расчёты modelled; формулы/input_paths/algorithm/version/hash видны.
- Снимок профиля/зоны передаёт клиент; приватная беседа по ID не читается,
  профиль не подтверждается/не меняется, AnalysisRun не создаётся.
  Draft разрешён для моделирования с warning. Зона — непроверенная context reference,
  OSM-score не принимается и не влияет на финансовую математику.
- README, FINANCE_ENGINE.md, ADR-0006, явный редактируемый demo input/result JSON,
  `scripts/eval_finance.py` для HTTP + независимого integer/Fraction эталона.

## Проверки

- `uv run --locked --project apps/api pytest apps/api/tests/test_finance.py -q`:
  **34 passed**, включая HTTP TestClient integration без зависимости от БД.
  Формулы/3 сценария, округление/копеечная маржа, zero sales/fixed,
  отрицательные результаты, денежные лимиты, invalid ratio/check/days/count,
  provenance/факты/синтетика, budget unknown/shortfall, override/sensitivity,
  пересчёт, source paths, реплей/Decimal context и независимость от зоны.
- `uv tool run --from prek==0.5.4 prek run --all-files`: Ruff lint/format,
  strict mypy, pytest, ESLint, TypeScript PASS; `npm --prefix apps/web run build` PASS.
- `docker compose --profile test run --build --rm db-tests`: **49 passed**,
  регрессия миграций, диалогов/конкурентности, геоимпорта, BA-007/BA-008.
  Новые финансовые тесты не требуют PostGIS и включены в обычный CI pytest.
- Compose healthy; `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke.ps1`: PASS.
- Реальный HTTP eval API :8000 и nginx :5173: PASS. Сверка трёх сценариев
  независимым Fraction/целыми копейками (без Decimal/engine helpers), startup/budget,
  полный identical replay, редактирование/recalculate, исключение зоны без изменения
  экономики. Прямой запуск 0.084/0.029/0.030/0.009 s, proxy
  0.087/0.028/0.015/0.029 s, один локальный запуск, не SLA.
- Docker/localhost проверены штатными разрешениями вне песочницы; для pytest —
  отдельный PYTEST_DEBUG_TEMPROOT. Настройки системы/ACL/volumes не менялись.
  Статус GitHub Actions подтверждается после push и сообщается в итоговом отчёте.

## Демо и ограничения

- `docs/examples/BA-009-coffee-input.json` — открытая synthetic-модель кофейни,
  не реальные цены Казани. Бюджет пользователя 2000000; startup без резерва 1500000,
  резерв 300000, всего 1800000, модельный остаток 200000 ₽.
- Fixed: аренда 80000, payroll 180000, utilities 20000, other 20000 ₽/месяц;
  30 дней. Check/sales/day/ratio: 250/60/0.40; 300/100/0.35; 350/130/0.32.
  Revenue: 450000/900000/1365000; variable: 180000/315000/436800;
  operating result: −30000/285000/628200 ₽; BE: 67/52/43 продаж в день.
- Input содержит настоящую архивную ссылку на зону BA-008; цены/продажи из OSM
  не выводятся. Geo dataset/version и реальные карты — в GEO_DATA/CANDIDATE_ZONES/
  ZONE_RANKING.md и прежних примерах. Повторный импорт для BA-009 не требовался.
- Operating result до неучтённых налогов/амортизации/процентов/прочих статей,
  не чистая прибыль/денежный поток. Нет payback/loan/cashflow schedule,
  сезонности/ликвидности/оборота запасов, верифицированных помещений и спроса.
  Payroll/ratio/other включают лишь явно принятые расходы; пропуски не становятся
  нулевыми реальными обязательствами. Budget fit — только сравнение модели.
- Нет скрытых rent/demand defaults и банковских условий. Независимая сверка
  доказывает арифметику, не коммерческую достоверность допущений.

## Следующий шаг

1. Проверить PR BA-009 и CI; объединить только по решению владельца.
2. После отдельного разрешения — BA-010 по PROJECT_PLAN.md, frontend поверх DTO.
3. Для реальных решений заменить synthetic-вводные проверенными источниками
   и расширить финансовую модель явно, не маскируя отсутствующие статьи.
