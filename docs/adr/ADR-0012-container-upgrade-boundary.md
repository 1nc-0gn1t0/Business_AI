# ADR-0012 · Container upgrade boundary

27.10.2026, H-06-FU; implementation tested, deployment/risk acceptance pending owner review.

Keep PostgreSQL major17. Upstream PostGIS3.5 tags are no longer maintained;
3.6 moves Debian/glibc. Minor PG compatibility does not make old text indexes safe
under a new libc. Use encrypted logical dump/restore into a fresh cluster, preserving
the old cluster and application version for a separately controlled rollback.

The derived PG17.11/PostGIS3.6.4 image starts as postgres without gosu/capabilities.
It refuses unmarked existing PGDATA and non17 major before upstream startup. A final
initialization script writes a marker only for a new initialized cluster. This guards
operator mistakes, not a hostile host administrator. Never forge the marker to bypass
dump/restore. No application schema/domain algorithm is changed.

The normal H-04-FU verifier retains exact-version checks. A separate opt-in isolated
drill permits an explicit version transition while preserving all public fingerprints,
indexes and known extension names. Arbitrary user schemas/globals need additional proof.
Spatial runtime remains part of geo fingerprints; old immutable reports remain intact.

CI image gate blocks reported-fix Critical/High, EOSL and incomplete/stale scans.
Unfixed/unassessed findings remain visible and keep release baseline OPEN; a successful
job is not an owner-approved exception or production readiness. No automatic deployment,
cleanup, model download, data cutover, downgrade or scanner suppression is introduced.

Evidence and owner procedure: [CONTAINER_UPGRADE](../CONTAINER_UPGRADE.md),
[H-06-FU report](../qa/H-06-FU_CONTAINER_REPORT.md).
