# H-04-FU · Backup encryption и локальное recovery rehearsal

26.10.2026. База: PR#22/c39d4ac объединён в main930b8e4. Ветка
`codex/H-04-FU-backup-recovery`. Это follow-up H-04, не новый продуктовый этап.
Машинные результаты: [evidence JSON](H-04-FU-evidence.json).
Инструкции: [BACKUP_RESTORE](../BACKUP_RESTORE.md), [миграции](../MIGRATIONS.md).

## Подтверждённый результат

- Новый backup pipeline действительно шифрует dump **до записи на диск**. Поток
  `pg_dump → bounded Python buffer → age → ciphertext`; отдельно шифруется manifest
  источника/counts/schema. Публичный manifest содержит только ID, UTC-время, размеры
  и SHA ciphertext. Никаких plaintext dump/metadata в постоянном хранилище.
- age **v1.3.2**, официальные Windows/Linux amd64 releases с pinned SHA256; BSD-3-Clause.
  X25519 recipients, authenticated encryption реализует age, не наш код.
  [Release](https://github.com/FiloSottile/age/releases/tag/v1.3.2),
  [формат/документация](https://github.com/FiloSottile/age).
  Проверены SHA официальных assets, отдельная Sigsum verification не внедрялась.
- Два реальных интервальных watch-запуска с PostgreSQL успешно завершились. Отдельное
  временное Windows Task Scheduler задание **реально выполнилось по trigger**, exit0,
  snapshot age8.823s при завершении. Задание удалено; постоянные задания не включены.
- Полное локальное clean-project восстановление: **53.157s**, включая backend/web и
  настоящий Qwen HTTP smoke. Оригинальные данные/контейнеры/volumes не переключались.
- Counts/row SHA всех19 public tables, schema/indexes/extensions/server version
  совпали. Кириллица/₽, immutable PDF/JSON bytes, owner404 для чужого токена,
  история/профили/consents/отзыв/receipt/audit/provenance сохранены.

## Ключи и границы доверия

Для проверки созданы **только временные синтетические identities**. Реальный ключ
владельца не создавался. Backup job получает лишь публичный recipient. Identity
вне Git и storage; в CLI передаётся путь, не значение. Новые каталоги защищаются
0700/0600 либо Windows ACL (current owner/SYSTEM/Administrators; OWNER RIGHTS
разрешён только при проверенном владельце). Ключевые bytes не идут в stdout/logs/CI artifacts.

При restore age сначала полностью аутентифицирует metadata и dump, сверяется
plaintext SHA, **потом** создаётся новая БД. На этой стадии допускается private
TemporaryFile с delete-on-close, в том числе при исключении; остатки проверены.
Backup не требует приватного ключа. Целостность routine status — successful pipeline
и cipher SHA; `verify --identity` отдельно доказывает authentication, не подменяется
одной checksum. Последняя native-scheduled копия отдельно прошла этот verify.

age не подтверждает авторство отправителя: архив принимать только из доверенного
ACL-protected хранилища. pg_restore исполняет SQL источника. Администратор/скомпрометированный
хост, потеря ключа и физический диск за пределами локальной проверки.

## Объёмы, выбор фикстуры и оборудование

До генерации: около420GB свободно на C:, Docker memory limit8204406784 bytes,
16 vCPU, host16GB RAM/i7-11800H, RTX3050Ti4GB. GPU не используется backup-инструментами.
Оценка: каждая БД <256MB, dump <100MB, с копиями <1GB; не огромный городской импорт.

| Показатель | Small | Large |
|---|---:|---:|
| Source DB, bytes после seed | 17 542 291 | 58 150 035 |
| Restored small DB, bytes | 17 411 219 | — |
| Гостевые профили/сессии | 2 | 200 |
| Сообщения | 4 | 16 438 |
| Ревизии | 4 | 8 518 |
| Согласия, включая withdrawal | 5 | 303 |
| Drafts / receipts | 2 / 1 | 52 / 51 |
| Audit events | 9 | 457 |
| Сохранённые PDF/JSON reports | 1 | 199 |
| POI | 153 | 20 153 |
| Road edges / graph versions | 5 / 1 | 4 905 / 2 |
| Ciphertext dump+metadata, bytes | 133 883 | 11 312 502 |
| Backup, s | 4.375 | 8.406 |
| Small restore auth / restore / verify, s | .688 / 2.250 / 2.297 | — |

Large — модель ограниченной локальной beta, близкая к **существующим** stock caps:
199/200 reports, 16438/20000 messages,8518/10000 revisions. Не production capacity test.
Частотные caps увеличены **только в процессе fixture seed**, runtime API оставлен
с обычными H-02 limits. Ручные исторические fixture inserts не заменяют chat tests.
Пользователи/переписка/финансы/дополнительная география синтетические.151 POI — уже
хранимый маленький OSM test extract, оставшиеся20k и grid2500nodes/4900edges явно
авторские test data. Нет загрузки Overpass и реальных персональных/банковских данных.
Zones сохранены в настоящем report snapshot, расчёты выполняли штатные сервисы.

После autovacuum physical large DB стала58346643 bytes без изменения логических
fingerprints. Физический размер restore может отличаться от source (heap/index layout).
PostgreSQL17.5/PostGIS3.5.2. Проверены валидность/SRID4326 POI и walk geometries.

## Полный локальный RTO

Независимый wall clock от начала подготовки нового проекта до успешного HTTP smoke:
**53.157s**, на данном наборе меньше цели60min. Фазы:

| Этап | Время, s |
|---|---:|
| Подготовка private workspace, UUID project, проверка cached images | 1.922 |
| Получение локальной зашифрованной копии | .016 |
| Проверка ciphertext SHA/размеров | .015 |
| Расшифровка, authentication, plaintext SHA | .844 |
| Чистый PostgreSQL/PostGIS startup | 5.297 |
| createdb + pg_restore | 3.656 |
| Schema/extensions/counts/fingerprints | 5.438 |
| Alembic check | 2.579 |
| Backend/frontend startup + health readiness | 3.468 |
| HTTP readiness | .110 |
| Owner/history/receipt/audit/geo/finance/bank/PDF/JSON + настоящий Qwen | 28.547 |

Raw metric `06…including_stage05=8.953s` включает startup5.297s; в таблице он
вычтен, чтобы не суммировать дважды. Остаток wall clock — orchestration/ACL/key/file
checks. Сумма отдельных фаз не является главным измерителем; raw total независим.
Qwen — установленная `qwen3:4b-instruct-2507-q4_K_M`, реальный extraction_mode=ollama,
кофейня/Казань/2млн правильно сохранены. Это один smoke, не повторный полный LLM eval.

**Условия:** рабочий Windows/Docker host; образы API/DB/web, age и модель уже доступны
локально; оператор имеет identity. Созданы новая network/volume/cluster, не clone
старого volume. Не измерены переустановка ОС/Docker, утрата ноутбука, скачивание образов/
весов с нуля, offsite доставка, восстановление потерянного ключа. Поэтому это полный
**локальный** rehearsal всех11 этапов, не универсальная production disaster SLA.

## RPO и автоматизация

Рабочее расписание предложено12h backup + hourly status, StartWhenAvailable, один
запуск задания и OS file lock на storage root. `watch` — переносимый foreground
runner с12h интервалом после завершения попытки; сам не daemon/service и не стартует
после перезагрузки без оператора/планировщика. Native wrapper проверяет exit code и
сохраняет короткие private logs, events фиксирует последнее успешное/неуспешное действие.

Observed age последней успешной native-копии при negative probe: **510.177s**
(8min30s); при завершении задания8.823s. Последняя копия прошла реальный age verify.
Временная шкала для «пропуск >24h» проверена управляемым clock, без ожидания25 часов:
ровно24h OK,24h+1s STALE, CLI exit2. При новых копиях RPO считается по **последней**,
а не произвольно выбранной старой копии. Ошибка попытки не меняет previous good copy;
status дополнительно сигнализирует last_attempt_failed даже при ещё свежей копии.

Ни расписание в XML, ни два тестовых запуска не доказывают суточную эксплуатацию.
Постоянные задачи **не установлены**. После ручной активации RPO≤24h условен:
host/пользовательский scheduler работают, Docker доступен, destination исправен,
backup успевает завершиться и оператор реагирует на ошибки. Выключенный/спящий
ноутбук, unlogged user, отказ диска/потеря всех локальных копий нарушают цель.
Нет PITR/WAL или независимого offsite; возможна потеря всех writes после snapshot.

## Отрицательные проверки

| Случай | Фактический результат |
|---|---|
| Неверный/отсутствующий identity, отсутствующий file | REFUSED; новый target не создан |
| Тампер/усечение ciphertext с пересчитанным public SHA | REFUSED настоящим age authentication; target не создан |
| Existing target | REFUSED; полные before/after fingerprints неизменны |
| Остановленная **только rehearsal** DB | REFUSED; после запуска прежние fingerprints совпали |
| Реальный pg_restore backend принудительно завершён | REFUSED; transactional rollback,0 public tables в новом target |
| Producer/encryption timeout/KeyboardInterrupt | Нет опубликованной partial backup; ciphertext staging очищен |
| Ошибка записи destination | PermissionError fixture; предыдущая исправная копия сохранена |
| Два процесса с одним storage root | OS lock исключает второй; после завершения slot освобождён |
| Retention | Dry-run по умолчанию, keep≥1, PIN не удаляется; последний хороший bundle сохранён |
| Secrets/plaintext leftovers | Secrets не в logs/репозитории; restore TempFile/staging очищены |

FS PermissionError контролировался unit fixture; физическое отключение диска не
производилось. Lock действует на один shared root и host OS, не распределённо.
Ошибки запуска native Task сначала воспроизведены, затем исправлены canonical paths:
AppData virtualized packaged host отличался от native Task/Docker. UTF-8 чтение
JSON задано явно; Linux/Windows paths не должны зависеть от console encoding.

Первый clean-cluster restore выявил readiness race: Unix-socket pg_isready считал
temporary init server готовым, затем initdb restart прерывал restore. TCP readiness
устранил причину; Compose health теперь использует127.0.0.1. Рабочие контейнеры
не пересоздавались. Ранние ошибки generator (version pin, fixture rate caps,
SQL JSON binding) исправлены; финальные small/large seed+read checks PASS.

## Регрессия и остаточные действия

Backend quick332PASS;102DB SKIP выполнены отдельно:PostgreSQL/PostGIS102PASS без XFAIL.
Crypto17PASS с реальным age; extended102PASS/1550 property examples; frontend43PASS;
Chromium24PASS; Ruff/mypy/TS/build/prek/Compose smoke PASS. Финальный SHA/CI — в PR.
Продуктовые API/DTO/формулы/гео/банк/LLM orchestration и immutable reports не менялись.

Первый Ubuntu CI завершился331PASS/1FAIL: тест watch подменял общий `time.sleep`,
перехватывая внутренние Linux `subprocess.wait` backoff sleeps. Ошибка воспроизведена
локально на Linux с настоящим age. Исправлена точка injection (только scheduler
`wait_interval`), assertion ровно одного ожидаемого интервала сохранён. Linux crypto
17PASS после исправления; предыдущий failure не засчитывается как PASS, финальный
CI сверяется на новом SHA.

**OPS-ENC: инженерная реализация и rehearsals подтверждены.** Для реальной эксплуатации
владелец должен создать собственный ключ/custody, выполнить backup/restore smoke,
включить расписание и проверить LastRunTime/LastTaskResult/status. Исторические F-00/
H-04 plaintext dumps сохранены по требованию, с прежним SHA/ACL: они **не стали
зашифрованными**. Нужен owner-controlled перенос/шифрование после настройки ключа,
без удаления единственного baseline до проверенного восстановления.

Cluster roles/ACL/globals, OS/image/model disaster rebuild, offsite/ключевая резервная
копия, постоянный monitoring и длительная RPO-история остаются эксплуатационными
условиями. Полный QG-OPS/RC этим PR не закрывается. H-05/H-06/BA-017/018 не начаты.
