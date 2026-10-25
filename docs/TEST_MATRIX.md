# BA-016 · матрица качества

Дата: 25.10.2026. Исходный main: `ea0354e` (PR #15 merged).
Результаты относятся к локальному прототипу, не к банковскому production/pilot.

## Методика и счёт

Считаем уникальные pytest/Vitest test IDs, а не число assert или повторных запусков.
Шесть property-тестов считаются отдельно от их 1550 сгенерированных примеров.
72 интеграционных теста пропускаются без PostgreSQL, но отдельно выполнены с PostGIS.
Машиночитаемый реестр: [BA-016-test-results.json](evals/BA-016-test-results.json).

| Группа | Фактический результат | Среда |
|---|---|---|
| API, включая extended | 352 PASS, 72 SKIP без БД | Windows, Python 3.12 |
| PostgreSQL/PostGIS | 72 PASS, 0 FAIL | Linux Docker, временные UUID-БД |
| Vitest | 35 PASS | явно mock API |
| Уникальные именованные проверки выше | 459; из них 453 обычных и 6 property suites | повторы не суммируются |
| Hypothesis | 1550 passing examples, 0 counterexamples после уточнения oracle | seeds 16001–16006 |
| Browser | 18 mock + 3 real PASS | [E2E_REPORT](E2E_REPORT.md) |
| Qwen | 61 уникальный диалог, 25 многотуровых, 123 шага на полном прогоне | см. [LLM_EVALUATION](LLM_EVALUATION.md) |

Новая pairwise-матрица `PAIR-001…072` покрывает все пары 12 отраслей × 6 городов,
12 отраслей × 6 бюджетов и 6 городов × 6 бюджетов. Это проверка сохранения параметров,
финансового контракта и сброса подтверждения, **не** доказательство наличия геоданных
или отраслевой модели для каждой комбинации. Негативные DTO — ещё 23 случая.

## Функциональность, зависимости и риски

| Требование / риск | Доказательство | Ограничение |
|---|---|---|
| BA-001/002: сборка/health/CI | `test_health`, Compose smoke, prek, build | health не доказывает готовность LLM |
| BA-003: строгие DTO/provenance | `test_contracts`, migrations constraints | пользовательские attestation не независимая проверка |
| BA-004: гостевая изоляция, правки, история | `integration/test_conversations`, concurrent edits/inference | нет полноценной учётной записи/восстановления утраченного token |
| BA-005: извлечение и ошибки Qwen | `test_llm`, versioned live corpus, 502/503/504 rollback | 2 устойчивых ошибки city; ручная проверка обязательна |
| BA-006: импорт/версия/coverage | `test_geo`, `integration/test_geo` | OSM неполон; нет данных других городов |
| BA-007: ограничения/геометрии/детерминизм | candidate policy + integration candidates | зоны не свободные помещения |
| BA-008: веса/сигнал/сравнимость | scoring + integration ranking + property coverage | proxy-рейтинг, не спрос/прибыль |
| BA-009: деньги/BE/отрицательный результат | finance + rational oracle, rent metamorphic | нет налогов, кредитного cash flow, рыночной аренды |
| BA-010: интерфейс/возврат/ошибки | Vitest, REL-* Chromium, real flows | только Chromium; accessibility не сертифицирована |
| BA-011: неизвестные условия/старые продукты | bank tests, stale/unverified/retired cases | каталог демонстрационный, не действующие тарифы |
| BA-012: согласия/IDOR/replay/audit | integration leads, LeadFlow tests | нет реальной отправки в банк |
| BA-013: топология/барьеры/неполный граф | walking tests + три реальные точки | отсутствие маршрута не физическая недоступность |
| BA-014: origin/version/no fallback | provider unit + integration, DataSources UI | GHSL/licensed unavailable |
| BA-015: owner/snapshot/старые данные/PDF | reports integration + pypdf + UI download tests | мягкий deadline; нет глобальных квот/retention |

Самые опасные цепочки: profile revision → stale report/draft; revoke consent → submit;
новый источник → прежние fingerprints; LLM → непроверенная сумма; чужой owner ID → export.
Им посвящены отдельные транзакционные/негативные тесты, а не только happy path.

## Команды и группы

```powershell
# Быстрые обязательные проверки каждого push/PR: GPU/сеть модели не нужны
uv tool run --from prek==0.5.4 prek run --all-files
# Extended в CI отдельным шагом на Windows/Linux
uv run --locked --project apps/api pytest apps/api/tests -m extended --hypothesis-show-statistics
# PostgreSQL: фикстуры создают/удаляют только свои business_ai_test_UUID
docker compose --profile test run --build --rm db-tests
# Browser offline: 18 mock API сценариев
npm --prefix apps/web run test:e2e
# Security/regression (без DB; DB-варианты — профиль test выше)
uv run --locked --project apps/api pytest apps/api/tests/test_llm.py apps/api/tests/test_bank.py apps/api/tests/test_leads.py apps/api/tests/test_reporting.py apps/api/tests/test_health.py
```

Live Qwen и performance запускаются отдельно, команды — в соответствующих отчётах.
CI не скачивает веса, не использует GPU или банковские API.
Настройки генерации сверены с [официальным Hypothesis API](https://hypothesis.readthedocs.io/en/latest/reference/api.html):
`max_examples`, `seed`, shrinking; dev-версия фиксируется uv.lock.
При проблеме Windows temp используйте новый доступный каталог через
`PYTEST_DEBUG_TEMPROOT`, не меняя прав старого чужого `pytest-of-*`.

## Остаточные пробелы

Не выполнены: многочасовой soak, массовые одновременные пользователи, реальные
коммерческие источники/банк, независимый pentest, Firefox/WebKit, юридическая
проверка согласий. Не останавливались рабочие PostgreSQL/Ollama ради fault injection:
сбои моделируются контролируемым transport/dependency и отдельными API fixtures.
Сеть публичных тайлов может отказать; расчёты и векторные слои локальные, PDF без тайлов.
