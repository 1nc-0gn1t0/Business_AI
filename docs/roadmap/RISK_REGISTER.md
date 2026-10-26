# Post-MVP · реестр дефектов, рисков и внешних зависимостей

25.10.2026. Реестр утверждённого roadmap, обновлён результатами F-00;
добавлены H-01 triage, H-02 caps, H-03 inference lifecycle и H-04 recovery. Ответственный — владелец проекта.
`Подтверждено` означает код/артефакт, не новую эксплуатационную сертификацию.
P0-дефектов, **доказанных в ограниченном H-01 triage**, не выявлено;
непроверенные поверхности и нагрузки не объявляются безопасными.

Обновление F-00, 25.10.2026: roadmap утверждён владельцем; подготовлен
[baseline](../baselines/F-00_BASELINE.md). Выполнен базовый backup/restore drill,
но H-01/H-04 не закрыты: нет полного DR/previous-version upgrade/encryption policy.
Ниже исторические evidence сохранены; D-04 добавлен по фактической проверке F-00.

## Обновление H-04-FU · 26.10.2026

- PR#22/c39d4ac merged, main930b8e4; отдельная ветка `codex/H-04-FU-backup-recovery`.
  [Отчёт](../qa/H-04-FU_RECOVERY_REPORT.md), [измерения](../qa/H-04-FU-evidence.json).
- **OPS-ENC — инженерная часть подтверждена:** настоящий age1.3.2, потоковый encrypted
  dump/metadata, atomic publish, pre-DB authentication, private controlled restore
  TempFile, no plaintext residues. Wrong-key/tamper/truncate/missing/cancel tests PASS.
  Owner production key не создавался. Реальное внедрение/ключи/custody — у владельца.
- **OPS-RPO частично подтверждён:** два реальных watch runs и scheduled native trigger
  exit0; последняя копия отдельно age-verified, observed age510.177s; управляемый clock
  24h+1s → STALE. Постоянный scheduler **не включён**,24h availability/offsite не
  обеспечены. Нельзя закрывать RPO-обязательство до ручной активации и эксплуатации.
- **DB/app recovery подтверждён локально:** fresh project/cluster+restore+19 table
  fingerprints+HTTP owner/PDF/receipt/geo/finance/bank+real Qwen, **53.157s** на58MB
  fixture/11MB ciphertext. Реальный pg_restore termination →0 partial tables.
  Это не OS/key-loss/model download/offsite disaster SLA и не весь QG-OPS.
- Найденная bootstrap readiness race исправлена TCP pg_isready (temporary init
  Unix socket больше не означает ready); working containers не пересоздавались.
  Native Task failure в packaged AppData исправлен canonical paths, реальный rerun PASS.
- **R-12 остаётся частично открытым/P1 до RC:** F-00/H-04 старые plaintext archives
  сохранены по требованию и не зашифрованы задним числом; owner-controlled migration
  после ключей и проверенного restore. Lost-key/offsite/24h monitoring/cluster globals/
  host rebuild не подтверждены; supply-chain/secret scanners остаются H-06.
- Новых подтверждённых P0 не выявлено на scope. H-05/H-06 и BA-017/018 не начаты;
  дальнейший технический этап — только после review/merge и разрешения владельца.

## Обновление H-04 · 26.10.2026 (исторический)

- H-03 PR#21/fb74296 объединён, шесть CI SUCCESS; main869453f. H-04 branch
  `codex/H-04-migrations-restore`. Результаты: [migration policy](../MIGRATIONS.md),
  [backup runbook](../BACKUP_RESTORE.md), [агрегаты](../evals/H-04-migration-restore.json).
- **D-04 исправлен, regression PASS:** старый env воспроизводит ложный TIGER DROP;
  новый scoped public/extension-owned filter даёт clean check, но выявляет реальные
  extra table/column. Extension/role search_path рабочей БД не изменены.
- **R-12 частично закрыт:** populated0007→0008, retry после SQL error/backend termination,
  все17 app tables/FK/unique/provenance, private backup/restore19 public tables,
  owner/receipt/PDF/JSON и F-00 image read smoke PASS. CLI downgrade default-deny;
  existing target/invalid archive отказы проверены без удаления рабочих данных.
- **OPS-ENC / R-12 остаётся P1 до RC:** backups не зашифрованы; ACL не заменяет
  encryption. Конкретный отдельный блок2–4ч: pinned age recipient encryption,
  независимое custody/recovery ключа, encrypted staging/offsite, real roundtrip и
  tamper/wrong-key tests. Выбор хранилища/ключа требует владельца; не начат автоматически.
- **OPS-RPO / R-12 требует проверки:** RPO≤24h не обеспечен scheduler/monitoring;
  restore3.281s — маленькая fixture DB, не полный RTO≤60min. Cluster globals/model/host
  DR, encrypted offsite и permissions переноса на другой host не доказаны. Retention
  policy предложена, автоматическое удаление не настроено. Scanners остаются H-06.
- Новых подтверждённых P0 на выполненном scope нет. QG-PR локально пройден; QG-OPS
  только migration/DB recovery subset, не весь RC gate. H-05/H-06, D-01…03 и
  BA-017/018 не выполнены/не начаты. H-05 — только после отдельного разрешения.

## Обновление H-03 · 26.10.2026 (исторический)

- **H01-P1-02/R-02: исправлен в H-03**, ожидает review/merge. До изменения — 1 idle
  transaction/1 checked-out; после —0/0, разные read/write Session, повторные owner/
  version/consent revision checks. Старый XFAIL дал XPASS, затем стал обычным PASS
  с сохранённым desired assertion. Пул из одного connection обслуживает пять чтений
  при blocked inference; реальная Qwen:538 samples, peak pool0/idle transaction0.
  [Методика/границы](../PERFORMANCE.md), [данные](../evals/H-03-inference-pool.json).
- Queue overflow, wait timeout, HTTP disconnect active/queued, revoke/regrant, city/
  budget edits и SQL error после flush проверены с отсутствием частичных записей.
  **Новых P0 не выявлено** в выполненном scope; 95 Postgres/PostGIS PASS без XFAIL.
- Ограничения R-02/R-04: один процесс/loop, direct Ollama и другие replicas вне queue;
  произвольный sync thread нельзя немедленно остановить, lease сохраняется до его
  завершения. Для Ollama API работает async cancellation. Disconnect после commit
  требует reread/CAS; exactly-once HTTP delivery не обещается.
- Полный GPU cancellation/нагрузка/8ч soak/p95 не сертифицированы. R-04 не закрыт
  целиком, QG-OPS подтверждён только в части H-03. H-04…06/D-01…04 и внешние gates
  сохраняются. BA-017/018 не начаты, следующий H-04 требует разрешения владельца.

## Обновление H-02 · 26.10.2026 (исторический)

- **H01-P1-01/R-01/R-03:** подтверждённый пробел закрыт для текущего loopback,
  single-worker deployment: 18 write API, bounded ASGI/DTO, общие persistent quotas
  PostgreSQL и process-local admission; доказательства отказов без побочных эффектов
  и параллельной атомарности — [API_LIMITS](../API_LIMITS.md) и
  [SECURITY_TEST_REPORT](../SECURITY_TEST_REPORT.md). Не объявляем полную защиту от DoS.
- **H01-P2-01:** исправлен standard request-validation422, assertions теперь PASS
  вместо strict XFAIL; raw input/context/arbitrary extra keys не отражаются.
- **H01-P1-02/R-02:** подтверждён, **открыт H-03**, соответствующий XFAIL сохранён.
- **R-04:** предварительная защита admission реализована, hard execution bounds/
  реальная CPU/lock нагрузка требуют Q-04/H-03; не закрыт целиком.
- **R-09:** existing owner/consent/idempotency tests повторно PASS; public accounts,
  XSS/TTL/retention не реализованы. Общую локальную квоту можно исчерпать новым guest
  в пределах общего window, но нельзя превысить её новыми ID/restart. Stock rows
  координируются БД; временные/concurrency лимиты **не multi-worker**.
- D-01…04, external/legal/data quality и остальные незатронутые риски сохраняются
  в прежних статусах. Новых P0 не обнаружено в выполненном bounded scope.
- H-02 не разрешает H-03/исследования автоматически. Порядок, принятый владельцем,
  сохранён; BA-017/018 — отдельный невыполненный трек.

## Срез H-01 · 25.10.2026 (исторический)

Подробные evidence/reproducer/expected/impact/regression/files:
[SECURITY_TEST_REPORT](../SECURITY_TEST_REPORT.md). Технический счёт текущего triage:
**0 P0, 2 P1, 1 P2**, не сумма исторических строк и не гарантия отсутствия иных дефектов.

| ID | Severity / статус | Факт / действие |
|---|---|---|
| H01-P1-01 | P1 · Подтверждён | Full-profile city4096 accepted; нет global guest/message budgets. Объединяет R-01/R-03; bounded probe, не DoS. H-02 |
| H01-P1-02 | P1 · Подтверждён | Idle DB transaction во время controlled inference подтверждена pg_stat_activity в UUID-БД; R-02. H-03 |
| H01-P2-01 | P2 · Подтверждён | 422 возвращает synthetic input самого отправителя; не чужие данные/секрет сервера. H-02/H-05 redaction review |
| Owner/CAS/consent bypass, duplicate receipt, partial commit | P0-гипотезы · Не подтверждены | Существующие tests повторно PASS; новые post-flush rollback tests PASS. Открытых доказанных P0 нет |

Три strict XFAIL — воспроизведённые открытые finding probes, **не PASS**. Исправления
не внесены. H-01 закрывает triage, не H-02/H-03 и не нагрузочные/пилотные gates.
Операционный порядок по решению владельца: F-00 → H-01 → H-02…06 → UX → U → UI → QA → RC.
Карточки/исследовательские задачи не переписаны. BA-017/018 — отдельный трек;
сроки/зависимости UX/U нужно отдельно подтвердить, они не сняты автоматически.

### Статус каждого ранее зарегистрированного риска в пределах H-01

| Записи | Статус H-01 | Предел / следующий владелец работ |
|---|---|---|
| D-01/02 | Подтверждены историческим BA-016 evidence | Live Qwen не повторялся; U-03/U-04 |
| D-03 | Подтверждён кодом, без нового browser run | UI/workspace persistence U-10/U-11 |
| D-04 | Подтверждён F-00; повторно не испытывался | Никаких schema changes; H-04 |
| R-01/R-03 | Подтверждены как отсутствие политики/caps | H01-P1-01; настоящий DoS не подтверждён; H-02 |
| R-02 | Подтверждён контролируемым DB probe | H01-P1-02; pool starvation требует проверки; H-03/Q-04 |
| R-04 | Требует дальнейшей проверки | Мягкие checkpoints видны в коде; реальная CPU/lock нагрузка не измерялась; H-02/Q-04 |
| R-05/R-06/R-07 | Подтверждены кодом/F-00, не новые security defects | Universal refs/sector/city support вне H-01; U-00…12 |
| R-08 | Требует дальнейшей проверки | OSM ground truth/comprehension не измерены; UX/geo validation |
| R-09 | Требует дальнейшей проверки | Header/owner cases уже покрыты и повторно PASS; XSS/TTL/accounts/retention — H-02/BA-020/P-01 |
| R-10 | Уже покрыт существующими тестами в серверной части | Consent/revoke/audit повторно PASS; WORM/legal не подтверждены, внешние gates остаются |
| R-11 | Уже покрыт существующими тестами в серверной части | Mock/expired catalogue cases PASS; текущие банковские условия не подтверждены |
| R-12 | Требует дальнейшей проверки | F-00 restore evidence сохранён; scanners/previous-schema DR/encryption не выполнены; H-04/H-06 |
| R-13 | Требует дальнейшей проверки | Cross-browser/a11y не запускались; Q-02 |
| R-14 | Требует дальнейшей проверки | Полного load/soak/restart не было; Q-04/Q-06 |
| R-15 | Подтверждено отсутствие research evidence | BA-017/018 отдельным треком, не отменены; это не security P0 |
| R-16 | Требует дальнейшей проверки | Brand/legal references не перепроверялись; UX-03 |
| R-17 | Подтверждены ограничения ресурсов/один разработчик | Длительность/throughput не benchmark; WIP=1, H-05/Q-04 |
| R-18 | Требует дальнейшей проверки | External availability не тестировалась; pinned F-00 preserved, H-05/U-08 |

## Исторический реестр и задачи закрытия

| ID | Тип / состояние и доказательство | Последствие / приоритет | Задача и проверяемое закрытие |
|---|---|---|---|
| D-01 | Дефект модели, открыт: LLM-022 в [raw](../evals/BA-016-qwen-final.json) и repeats | Город теряется при иностранной валюте; P1 | U-04: независимые field deltas, RUB-only policy/clarification, regression + holdout + 3 real repeats |
| D-02 | Дефект модели, открыт: LLM-028 «Козани» | Ненормализованный город, пустой анализ; P1 | U-03: city registry/предложение подтверждения, no silent fuzzy match; 3 repeats |
| D-03 | Функциональный пробел, подтверждён: Finance useState, App/ReportExport lifecycle | Потеря черновика/выбора после reload/смены зоны; P1 | U-10/11: owner workspace resume и invalidation tests; отчёты BA-015 уже сохраняются, весь сценарий — нет |
| D-04 | Исправлен H-04; old-env FAIL/new-env PASS, actual TIGER fixture и app drift regression | Historical P1 закрыт в реализации; multi-schema вне текущего policy | Review/CI H-04; при новых schemas отдельный ADR/coverage; autogenerate всегда просматривать |
| R-01 | Эксплуатационный риск: глобальных quotas/rate limits/semaphore в app/compose нет | Истощение ресурсов при расширении доступа; P0 при подтверждённом DoS/публичной экспозиции, сейчас P1 | H-01→H-02: bounded controlled reproducer, caps/429; до gate только loopback |
| R-02 | Код подтверждает Session.begin + DB reads → LLM → final lock; impact не измерен | Connection pool занят во время inference; P1 | H-03: отдельные read snapshot/inference/write UoW, race tests и pool measurement |
| R-03 | Partial: ProfilePatch ограничен, общий BusinessProfile/NonEmptyText без аналогичных max; body bound только reports | Неравномерные API resource limits; P1 | H-02: каждый публичный DTO/body имеет budget и negative tests, no breaking v1 без решения |
| R-04 | Поздние report checkpoints мягкие, renderer в запросе/owner transaction | Долгий запрос/lock; P1 | H-01/H-02/Q-04: измерение, bounds/cancel semantics; worker вводить лишь по доказательству |
| R-05 | Текущая нормализация/банк/гео имеют независимые версии, отраслевые refs в профиле отсутствуют | Смешение старых/новых алгоритмов после расширения; P1 | U-00/02/12: pinned bindings, immutable v1 read, explicit stale |
| R-06 | 5 geo policy groups hardcoded, finance-template один; поддержка не равна валидации отрасли | Универсальность на словах, ложные цены/рекомендации; P1 | U-01/05/06/07: capabilities + разные template inputs/limitations; unsupported честно |
| R-07 | Один реально загруженный POI dataset, частичная Казань; graph уже bbox меньше | Обещание полного города/ложное отсутствие POI; P1 | U-08/09 + Q-01: layer coverage/date compatibility; второй bounded city, не «все города» |
| R-08 | OSM полнота физически неизвестна; proxies не ground truth | Рейтинг принят за спрос/прибыль; P1 | UX-01/UI-03: explanation comprehension test, expert field review отдельно; score ≠ forecast |
| R-09 | Guest bearer token в sessionStorage, accounts/expiry/recovery отсутствуют | Потеря доступа/XSS impact; P1 для local RC, blocker public pilot | H-01/H-02, P-01/BA-020: threat model, expiry/retention decision, auth design; не переносить в localStorage автоматически |
| R-10 | Consent/audit append-only на уровне приложения, не WORM; тексты demo | Нет юридически утверждённого основания пилота; внешний blocker | P-01/BA-020/021: legal/security review и approved texts; не удалять аудит без policy |
| R-11 | Six bank products demonstration/unconfirmed/cached_only | Восприятие как действующих условий ВТБ; P1 | U-12/UI-05: demo/blocked display; действующие условия только после проверки источника/владельца |
| R-12 | H-04-FU age pipeline/scheduled test/58MB local recovery53.157s PASS; old plaintext baseline, production custody/scheduler/offsite/host DR/scanners остаются | RPO условен, исходный plaintext и lost-key risk; P1 до RC | Владелец: реальные keys/backup/restore/schedule + historical archive protection; H-06/Q-06 scanners; не закрывать весь риск |
| R-13 | BA-016 Chromium/3 real paths; нет Firefox/WebKit/полной a11y оценки | Потеря функций на других браузерах/для screen reader; P1 | Q-02 + UI PR gates; реальные iOS/Safari проверки требуют устройства |
| R-14 | Нет soak/load/fault-restart evidence; BA-016 — небольшой serial benchmark | Неизвестные пределы, leaks/recovery; P1 | Q-04/06: 2 ч→8 ч isolated load, no external tile/Overpass load |
| R-15 | Нет реальных интервью/маржи/конверсий банка, BA-017/018 не реализованы | Недоказанный product-market/value case, дедлайн 31.10; P0 бизнес-приоритет | BA-017-* /018-*; честные evidence gaps, реальные действия владельца |
| R-16 | Визуальный live-аудит ВТБ заблокирован TLS; официального brand kit/right clearance нет | Выдуманные стандарты/ложная аффилиация; P1 | UX-03: approved references/rights; свои токены/шрифты, без bank logo до разрешения |
| R-17 | Один разработчик/4 ГБ VRAM/16 ГБ RAM, личная доступность неизвестна | Завышенный scope/сорванный срок; P1 | Лимит WIP=1, 25% reserve, scope caps, BA-017 recruitment early; RC estimate пересчитывать |
| R-18 | Overpass/public tiles best effort, лицензия не SLA; обновления надо делать заранее | Демо/импорт зависит от внешней сети; P1 | F-00/H-05/U-08: pinned snapshot + vector fallback, OSM policies; не prefetch чужие тайлы |

## Триаж и жизненный цикл записи

Новая запись: ID → reproducer/source → observed vs expected → severity → affected
version → owner/task → regression test → evidence → closed/accepted-until-date.
Исторические D-01/02 сохраняются и после исправления; не переписывать raw FAIL в PASS.
Если риск принят, указать разрешённый scope (например loopback demo), срок/условие
пересмотра и владельца. «Решим позже» без scope не закрывает P0.

На старте каждого PR проверить связанные записи; при контрольной версии — весь реестр.
Порог закрытия определяется [QUALITY_GATES](QUALITY_GATES.md), а не количеством тестов.
