# BA-016 · негативные проверки и безопасность

25.10.2026. Проверялось только локальное приложение/изолированные фикстуры.
Никаких нагрузочных/атакующих запросов к ВТБ, Overpass или другим сторонним API.

| ID | Проверка | Результат / доказательство |
|---|---|---|
| SEC-01 | чужие conversation/draft/report UUID + отсутствующий/чужой header | PASS: conversations/leads/reports integration, 401/404 |
| SEC-02 | stale expected_version, правка во время inference, параллельные drafts | PASS: реальная PostgreSQL блокировка/409, потерянных обновлений нет |
| SEC-03 | нет отдельного demo_lead consent, отзыв/смена текста после draft | PASS: leads integration; sender не вызывается |
| SEC-04 | отказ от marketing, сохранение базового профиля/аналитики | PASS: leads integration + LeadFlow/Vitest; отдельные purpose |
| SEC-05 | duplicate submit, idempotency, audit | PASS: одна локальная квитанция, `sent_to_bank=false` |
| SEC-06 | подмена payload, profile_version, продукта/условий | PASS: leads и reports integration |
| SEC-07 | stale report/source/demo disabled/historical | PASS: reports integration; historical не обходит policy |
| SEC-08 | corrupt provider/hash/version/license/origin | PASS: providers/import tests; нет synthetic fallback |
| SEC-09 | invalid LLM JSON, tools, SQL fields, timeout/outage | PASS: test_llm; 502/503/504 и rollback state/history |
| SEC-10 | live prompt injection/выдуманные geo/финансы/кредит | PASS на 5 сценариях × 2 полных прогона; не универсальная гарантия |
| SEC-11 | отрицательная/противоречащая цитате сумма | исправлено: clarification вместо ложного +budget; unit и 2 Postgres regressions PASS |
| SEC-12 | SQLAlchemy failure: риск SQL/secret в стандартном stack logging | business API теперь возвращает 503 `database_unavailable`, безопасный log; caplog/response assertions PASS |
| SEC-13 | guest token в download URL/PDF/JSON/браузерном логе | PASS для проверенных путей: protected headers, report fixtures, download E2E; traces/HAR выключены |
| SEC-14 | ресурсные границы, NaN/Infinity/длинные строки/нулевой чек | PASS: contracts/finance/reports/LLM tests; 4000 chars в UI и API |
| SEC-15 | устаревшие/unconfirmed/retired банковские продукты | PASS: bank tests; unknown не равен matched, credit_decision=not_assessed |

Бизнес-ошибка не выдаётся за успешную операцию. Повреждённый/обрезанный ответ Qwen
не записывает частичное состояние. Противоречащая денежная цитата теперь становится
запросом уточнения в нормальном ходе; корректные независимые поля допустимо сохранить.

Отчёты содержат только вымышленные входные данные и открытые OSM-агрегаты.
Live runner исключает идентификаторы бесед, токены и полную техническую историю.
Браузерные failure screenshots относятся к искусственным сессиям; не включены в Git.

Ограничения: это regression/security testing, не независимый pentest и не юридическая
сертификация. Нет глобальных rate limits/anti-abuse, пользовательских аккаунтов,
retention/delete workflow, многопользовательской эксплуатационной проверки. Гостевой
token остаётся bearer-secret в sessionStorage и может быть похищен при будущем XSS;
React экранирует текст, но это не заменяет отдельный аудит. Не публиковать локальные
сервисы в интернет без BA-017/018 и согласования владельца.
