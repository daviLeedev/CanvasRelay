# ADR 0002: PostgreSQL Metadata With Filesystem Media

| Field | Value |
| --- | --- |
| Status | Accepted |
| Date | 2026-08-01 |

## Context

CanvasRelay jobs and Library results must survive API and inference-provider
restarts. Library queries need relational filtering and stable cursor
pagination, while original images and videos need efficient streaming, range
requests, and future object-storage portability. Storing large binaries in the
same database would increase backup, vacuum, cache, and transfer costs without
improving those media delivery paths.

## Decision

- PostgreSQL is the metadata source of truth in Docker and hosted profiles.
- SQLAlchemy 2.x provides the repository implementation and psycopg 3 provides
  the PostgreSQL driver. Alembic owns schema migrations.
- SQLite implements the same repository contract for unit tests and optional
  standalone local use.
- Media binaries live under an explicit `DATA_DIR` filesystem store. Database
  rows contain relative storage keys, MIME, dimensions, byte size, SHA-256,
  provenance, and availability metadata; they never contain user-machine paths.
- Completed media is written atomically and Library thumbnails are generated as
  bounded WebP files. Original media is served only for detail and download.
- An idempotent CLI imports legacy SQLite rows without deleting the source.

## Consequences

PostgreSQL adds a runtime dependency and migration step, but gives durable
concurrent metadata access, indexes, JSONB for provider settings, and explicit
referential integrity. Filesystem media remains simple and fast for a local
portfolio runtime. A future object-store adapter can replace it without moving
binary payloads out of PostgreSQL.

Database and media writes cannot share one ACID transaction. CanvasRelay uses
atomic file replacement, checksums, missing-file metadata, and recoverable
cleanup behavior to make mismatches observable rather than silently deleting
jobs.
