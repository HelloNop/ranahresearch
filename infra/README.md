# Local development infrastructure (EPIC-002)

Run `make infra-up` from the repository root with Docker running. This starts
PostgreSQL + pgvector, Temporal + UI, and MinIO, waits for health, and creates
the S3 bucket idempotently. `make infra-check` checks vector SQL, Temporal cluster
and default namespace, an S3 put/get round trip, and UI HTTP access.

| Service | Host endpoint | Local connection |
| --- | --- | --- |
| PostgreSQL | 127.0.0.1:5432 | DB `ranahresearch`, user `ranah`, password `ranah-local-only` |
| Temporal | 127.0.0.1:7233 | namespace `default` |
| Temporal UI | http://127.0.0.1:8080 | local, no auth |
| S3 API | http://127.0.0.1:9002 | bucket `ranahresearch`, region `us-east-1`, path-style addressing |
| S3 console | http://127.0.0.1:9001 | access key `ranah-local`, secret `ranah-local-secret` |

These credentials are development defaults. Services bind to loopback only.
Copy `.env.example` to `.env` only to customize values; it is ignored by Git.
Compose consumes `.env`; the foundation API does not yet use infrastructure.
When overriding host ports or passwords, also update corresponding connection
URLs for future application clients. Do not use this stack as production deployment.

PostgreSQL stores app data and Temporal's separate `temporal` and
`temporal_visibility` databases in `postgres-data`. Sharing one database server
and bootstrap role is a local-only simplification; production requires separate
least-privilege roles. MinIO uses `object-data`. `make infra-down` preserves both.
Restarting services does not reset state. The vector initialization SQL runs only
on a fresh PostgreSQL volume; scientific schema migrations belong to EPIC-003.
No filesystem JSON is used as canonical scientific state.

If startup fails, inspect `make infra-logs` and `docker compose ps -a`. A Docker
socket error means the daemon is stopped or inaccessible. Port conflicts can be
resolved with the port variables in `.env`. Changing `POSTGRES_PASSWORD` after
initialization does not change the existing database password; restore the old
value or explicitly change the database role password. Never delete volumes as
an automatic recovery step.

Image tags are explicit. The Temporal configuration follows the official
[PostgreSQL setup](https://github.com/temporalio/docker-compose/blob/main/docker-compose-postgres.yml).
The [pgvector image](https://github.com/pgvector/pgvector#docker) supplies the
extension. MinIO is only a local S3-compatible service, not an application SDK
coupling. Redis is deferred because no implemented component needs it.

Application workflows and worker crash/resume verification belong to EPIC-005.
