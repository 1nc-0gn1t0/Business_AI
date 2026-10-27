# H-06-FU · Container security / safe upgrade · 27.10.2026

**Engineering hardening and isolated upgrade verified; release baseline OPEN.**
No owner-approved scanner exceptions. Remaining Critical/High cannot be silently
accepted, so H-01…H-06 is not declared fully closed for RC/UX transition.
PR25/f09c0cc merged as1bf0f5e; clean main, branch
`codex/H-06-FU-container-hardening`. No product/domain/schema/LLM orchestration changes.

## Method and classification

Trivy0.76.1, official checksum-verified binary. Downloaded a fresh DB:
UpdatedAt **2026-10-27T07:13:33.504287223Z**; all final before/after scans use this
same frozen cache, `--scanners vuln --skip-db-update`, complete image scans.
The initial default-cache probe was superseded by these frozen-cache results.
H-06's historical305Medium/42Unknown differs from this repeat306/41; do not mix dates.

[All505 Critical/High package rows](H-06-FU_TRIAGE.csv) include ID, image/phase,
package, installed/reported fixed version, origin/binary, reachability, action and
status. [Summary](H-06-FU_SCAN_SUMMARY.json) retains all severities/image IDs; no
unresolved row was removed because a test passed. A package occurrence is not a
unique advisory or demonstrated exploit. Counts below deduplicate within each image;
the union uses the highest vendor severity per ID across images.

| Image | Critical before→after | High before→after | Medium before→after |
|---|---:|---:|---:|
| API |0→0|8→8|29→29|
| DB |16→3|151→36|277→92|
| Ollama |0→0|46→0|57→21|
| Web unchanged |0→0|0→0|0→0|
| Unique union |16→3|174→36|306→107|

Final union also190Low/6Unknown. **166 original Critical/High IDs disappear,15 new
IDs appear in newer distro packages.** New findings are not hidden:
CVE-2026-107815, CVE-2026-107818, CVE-2026-107823, CVE-2026-12064,
CVE-2026-24882, CVE-2026-44168, CVE-2026-44171, CVE-2026-44172,
CVE-2026-48163, CVE-2026-48165, CVE-2026-49261, CVE-2026-85746,
CVE-2026-86047, CVE-2026-92262, CVE-2026-97380 (full IDs/package rows in CSV).

Classification:

- **Image upgrade/removal:** obsolete PG17.5 security issues, old Debian11 libraries,
  old Go in gosu and Ollama dependencies. Per-ID transitions remain in CSV.
- **Targeted removal:** API mount package, namespace/terminal administration binaries;
  shared-library/source-package matches remain8High. No fake package metadata cleanup.
- **No supported package fix reported:** remaining Debian13 matches. A real apt update
  in a disposable upstream container confirmed installed=candidate for libxml2,
  libmariadb3, util-linux, libtiff6 and PostGIS. This is not "no upstream fix exists".
- **Not applicable with component proof:** CVE-2026-49261 requires MariaDB server/Galera
  `wsrep_notify_cmd`. mariadbd/mysqld are absent; only client libmariadb3 is included
  via GDAL. Raw rows remain, with no scanner suppression/automatic risk acceptance.
- **Further review:** other native-library/driver paths; limited application-path
  inspection is not a complete VEX/pentest or proof against stolen SQL credentials.

## Remaining Critical/High: disposition

- **CVE-2026-6653 (Critical), libxml2**: Debian trixie marks vulnerable/no-dsa.
  PostGIS actually links libxml2. No app XML/GML/KML import/SQL endpoint found, but
  native/SQL surface remains. Do not replace stable ABI using unstable packages.
  [Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-6653).
- **CVE-2026-44172 (Critical), MariaDB client/source package**: Big5 escaping risk;
  client library is present, no application MariaDB connection. GDAL/native paths
  not exhaustively certified; keep unresolved. [Vendor package context](https://www.suse.com/security/cve/CVE-2026-44172.html).
- **CVE-2026-49261 (Critical)**: server component absent, as above.
  [Upstream advisory](https://github.com/MariaDB/server/security/advisories/GHSA-3p3m-4x7c-p4pw).
- **CVE-2026-73515 (High), PostGIS FlatGeobuf decoder**: no app FlatGeobuf route or
  ST_FromFlatGeobuf call. SQL users can still reach the extension. Newest supported
  3.6 package still matched; no pre-release3.7 or unsupported native rebuild introduced.
  [Vendor advisory](https://access.redhat.com/security/cve/cve-2026-73515).
- Other **36 unique High total**, including the above, cover util-linux/mount/nsenter,
  ncurses/infocmp, ACL, systemd-homed, Perl Archive::Tar, GnuPG, GDAL/FITS/TIFF,
  XML/curl and MariaDB families. Every ID/package appears in CSV. Nonroot, dropped
  capabilities, absent administration binaries, no DB host port and typed API reduce
  surface; none authorizes a blanket exception. Removing GnuPG's dependency closure
  would also remove GDAL/PostGIS (apt simulation proved this), so it was not done.

No demonstrated new P0 exploit. Unfixed/unassessed risks remain P1 release blockers;
legal/native/GPU redistribution and own application license remain H-06 obligations.

## Versions, digests and runtime hardening

| Component | Before | Candidate / shipped config |
|---|---|---|
| DB upstream |postgis/postgis17-3.5, digest01a6a70e41e6c4467c8f55f6063555ed72db2d6662cd0d571040d42eadaeb6f6|17-3.6, digest1ac10b2551ba84ae05db8e7da477afcd0a3fede99bcb7705da2ee157390cb095|
| Server/extensions |PG17.5/PostGIS3.5.2/Debian11.11|PG17.11/PostGIS3.6.4/Debian13.7|
| API upstream |Python3.12-slim digest12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f|same digest and Python/app dependencies|
| Ollama |0.40.8, digest2b8eecdb85aa6ea67c381c8ecffec04b2658496cf2821a8f88b0485bdff198e8|0.40.11, digestdea72d1e22270fe095b68fdf756d2b489d615643c5a2eaebbc5f569181e322d8|
| Web |H-06 nginx/base digests|unchanged|

Local derived image SHA256 IDs are in summary JSON, distinct from registry index
digests. DB childc1344008…; API child84ae7dc9…; not claiming bit-identical builds.

DB now runs as postgres999:999, cap_dropALL/no-new-privileges; gosu removed entirely
instead of relabeling its old Go findings. Guard refuses PGDATA17 without the new
initialization marker and any other major, even with a marker. Actual disposable
tmpfs probes exit64 and preserve sentinel/PG_VERSION; fresh initialization PASS.
Marker is written only after all upstream PostGIS init scripts finish.

API runtime removes mount via apt purge, nsenter/infocmp binaries by explicit path;
keeps Python, libpq, PDF libs and essential libraries. No supported-fix8High was
silently waived. Nonroot/cap_drop/no-new-privileges and H-02/H-03 guarantees retained.
No Python/npm version upgrade, no new service/DB technology or paid dependency.

## Filled DB, age and integrity

Used H-04-FU fixture/age pipeline, new source and target tmpfs clusters (768MiB each),
new UUID projects, no existing mounts/volumes. Host16GB RAM, Docker VM8.2GB, RTX3050Ti4GB;
about401GB free before setup. Bounded local-beta fixture, not production capacity.

Source **57,404,563 bytes** before adding optional extensions:200 profiles/sessions,
16,438 messages,8,518 revisions,303 consents incl withdrawals,52 drafts,51 receipts,
457 audit events,199 actual PDF/JSON reports,20,153 POI,4,905 walk edges/2graphs.
Synthetic data only plus the existing tiny permitted OSM test extract; no live import.

- Initial authenticated restore: public data/schema/index fingerprints equal.
- Second encrypted archive with **all five working extension names**,11,319,352 bytes,
  backup9.688s. Restored fuzzystrmatch1.2/plpgsql1.0 unchanged; postgis/topology/TIGER
  3.5.2→3.6.4. Exact counts/SHA for **19 public tables**, schema/index SHA and0invalid
  indexes equal. Full per-table fingerprints/cipher SHA in
  [safe recovery evidence](H-06-FU_RECOVERY_EVIDENCE.json).
- Authentication1.468s, restore3.782s, verification5.843s, total **11.093s**.
  This is crypto+restore+verification timing, **not a new full disaster RTO/SLA**.
  H-04-FU RPO/offsite/key-custody limitations remain; scheduling was not changed.
- Real target fixture API: owner404, profile/history, withdrawn consents,
  mock receipt/audit, provenance, Cyrillic/₽ and immutable PDF/JSON SHA PASS.
- New runtime generated PDF48,489bytes/JSON57,185bytes, no guest token. Existing
  old geo reference initially returned409: expected spatial_runtime fingerprint
  invalidation. Explicit API reranking refreshed it; fixture scores exactly equal.
  Old report bytes were not rewritten. /livez,/readyz, web and assets PASS.
- Actual wrong key, tampered ciphertext (even with recomputed public SHA), unavailable
  QA project: REFUSED/no new target DB. Existing target refused before restore.
  Delete-on-close plaintext files left no observed residue. H-04 tools unchanged.

The general encrypted restore still requires equal versions; separate bounded
upgrade tool permits only the tested transition. Additional real custom schemas,
user topology/TIGER data and cluster globals need owner validation before cutover.
No actual user DB migration or production RTO guarantee is claimed.

## Ollama / Qwen

Official0.40.11 release; same Qwen
`qwen3:4b-instruct-2507-q4_K_M`, manifest
`0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
No weights downloaded/modified; mounted existing model volume read-only in isolated
candidate containers. Cloud disabled, loopback-only, one model/parallel inference.

- Real BusinessAI API→Ollama→PG: coffee/Kazan/2m extraction_mode=ollama PASS,
  correct city/category/budget, **86.844s cold**,2,344,636,907VRAM bytes on RTX3050Ti.
- Warm direct structured probe:2.438s,39generated tokens.
- Separate container without GPU:10.422s,39tokens,0VRAM, same digest and valid JSON.
  CPU is a short server/structured-output smoke, not full API/browser dialogue.
- H-03 queue/CAS/cancellation tests run in regression; orchestration unchanged.
  No p95/full LLM evaluation or claim that cold/warm prompts are equivalent workloads.
  GPU candidate stopped before CPU test; original Ollama/container unchanged.

## Checks and operational limits

- Backend382PASS/104DB SKIP (separately104PASS on new PG/PostGIS); no XFAIL credited.
- Extended102PASS/1550 Hypothesis examples; frontend45PASS; Chromium mock27PASS;
  TypeScript/build PASS. New17 fail-closed/upgrade policy cases included in backend.
- Guard probes PASS; H-04 encryption/restore tests part of quick; actual negatives
  above independently exercised real DB and age. Final prek7hooks/Ruff/mypy124files PASS; exact HEAD CI is checked after push.
- New image gate: builds API/DB/web and scans all four runtimes, SHA-verified Trivy, one fresh DB,
  fails incomplete/error/stale/EOSL scans and reported-fix Critical/High. Local gate PASS
  with0fixableC/H; release status still **OPEN**. No blanket exceptions/ignores.
- Harness corrections: existing private context exclusive-write refusal after backup;
  temporary localhost health probe hit IPv6 (changed to127.0.0.1); Windows private
  state reader required explicit UTF-8. No product defect masked. Expected409 stale
  geo result required explicit recalculation, not a backend workaround.
- Working DB/API/web/Ollama and F-00/H-04 backups preserved. H-05 QA volume untouched.
  New QA DBs use tmpfs; no persistent user volume deletion or policy bypass.

## Decision / next action

Engineering result is reviewable; **security baseline remains unaccepted** until
remaining Critical/High have supported fixes or explicit owner-approved, scoped,
time-bounded dispositions. Proposed reassessment10November2026 is not an approved
exception expiry. Do not begin UX/U/UI/research automatically. Owner must separately
approve real deployment cutover and outstanding release risks.

Reproduction: [upgrade runbook](../CONTAINER_UPGRADE.md),
[checkpoint](H-06-FU_CHECKPOINT.md), [H-06 audit](H-06_SUPPLY_CHAIN_REPORT.md).
