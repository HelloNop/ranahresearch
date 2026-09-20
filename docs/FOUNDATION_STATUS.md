# EPIC-001 / EPIC-002 implementation report

Date: 2026-09-20.

## Initial state

The checkout contained only README.md and eight source-of-truth documents.
All eight documents were read before implementation. There was no Git repository,
application code, workspace configuration, test suite, CI, or local infrastructure.
No applicable AGENTS.md was present. No existing files were removed.

## Final structure

```text
.github/workflows/ci.yml
apps/
  api/src/ranah_api/
  web/app/
packages/
  domain/src/ranah_domain/
  agents/src/ranah_agents/
  llm/src/ranah_llm/
  literature/src/ranah_literature/
  evidence/src/ranah_evidence/
  review/src/ranah_review/
  statistics/src/ranah_statistics/
  documents/src/ranah_documents/
workers/{orchestration,research,document,statistics}/
prompts/
tests/
evals/
docs/
infra/postgres/
scripts/
```

## File changes

Modified existing file: `README.md` (retained the original product workflow and
specification list; added setup, commands, boundaries, layout, and branch strategy).

Existing files preserved unchanged:

- docs/PRD.md
- docs/SCIENTIFIC_METHODOLOGY.md
- docs/TECHNICAL_ARCHITECTURE.md
- docs/OPENDRAFT_ADOPTION.md
- docs/DATA_MODEL.md
- docs/AGENT_CONTRACTS.md
- docs/IMPLEMENTATION_ROADMAP.md
- docs/INDEX.md

New files:

- Root: `.editorconfig`, `.gitignore`, `.env.example`, `.python-version`, `.nvmrc`,
  `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, `Makefile`,
  `compose.yaml`, `THIRD_PARTY_NOTICES.md`.
- `.github/workflows/ci.yml`.
- API: `apps/api/pyproject.toml`, `apps/api/src/ranah_api/__init__.py`,
  `apps/api/src/ranah_api/main.py`.
- Web: `apps/web/package.json`, `tsconfig.json`, `next-env.d.ts`,
  `eslint.config.mjs`, `app/layout.tsx`, `app/page.tsx`.
- Each of the eight packages: `pyproject.toml` and `src/ranah_<name>/__init__.py`.
- `.gitkeep` in each of the four worker directories, `prompts/`, and `evals/`.
- `tests/test_foundation.py`, `scripts/smoke.py`.
- `infra/README.md`, `infra/postgres/init.sql`, `infra/s3-check.sh`.
- This report, `docs/FOUNDATION_STATUS.md`.

Git was initialized on `main`. No commit or remote was created. Generated
`.venv`, `node_modules`, `.next`, caches, and build artifacts are ignored.

## Technical decisions

- Python 3.12, uv workspace, Hatchling builds, one Python lockfile. Separate
  `ranah_*` import names avoid collisions such as Python's `statistics` module.
- Node 24, npm workspace, Next.js 16 / React 19, strict TypeScript; one npm lockfile.
- Minimal FastAPI liveness endpoint and static web page. No scientific product
  features, agent abstractions, provider SDKs, or migrations are implemented early.
- Logical modules remain part of a modular monolith. Worker directories reserve
  durable worker entry points for EPIC-005.
- PostgreSQL 16 + pgvector, PostgreSQL-backed Temporal and UI, local S3-compatible
  MinIO. Named volumes preserve database/object data, with loopback-only ports.
- Temporal uses separate databases within the local PostgreSQL server. Shared
  bootstrap credentials are development-only; application schema is EPIC-003.
- Redis is omitted until a component requires it.
- No OpenDraft implementation was adopted. The notice file records the procedure
  for actual future adoption; no copyright attribution was invented.
- All scientific architecture constraints remain intact, including distinct
  WorkRecord/Study/Evidence/Claim/Manuscript concepts and deterministic statistics.

## Acceptance

| Epic / criterion | Result |
| --- | --- |
| 001: repository builds | PASS: nine wheel/sdist pairs and Next.js production build |
| 001: Python imports | PASS: all eight module packages and API imported |
| 001: web starts | PASS: production server returned HTTP 200 |
| 001: API starts | PASS: Uvicorn `/health` returned HTTP 200 and expected body |
| 001: basic CI checks | Implemented; same commands passed locally |
| 001: structure/configuration/docs/notices/branch strategy | Complete |
| 002: PostgreSQL + pgvector | PASS: real vector SQL query |
| 002: Temporal + UI | PASS: cluster SERVING, default namespace, UI HTTP response |
| 002: local S3 | PASS: bucket bootstrap and put/get round trip |
| 002: one-command local infrastructure start | PASS: `make infra-up` |

GitHub-hosted CI execution and branch protection remain unverified/unconfigured
because there is no remote repository. This is not a local foundation blocker.

## Checks performed

- Test-first API smoke: pytest failed on missing `ranah_api.main`, then passed
  after the endpoint implementation.
- `make install check build`: locked installation, Ruff lint/format, strict mypy,
  two passing pytest checks, ESLint, TypeScript, Python builds, Next.js build.
- `make smoke`: real API and production web startup, HTTP checks, automatic teardown.
- `docker compose config --quiet`, `sh -n infra/s3-check.sh`.
- `make infra-up infra-check`: real PostgreSQL/vector, Temporal, S3, and UI checks.
- Restarted the four services, reran startup/checks successfully. Temporal's
  namespace ID remained unchanged, confirming its database state survived restart.
- npm reported zero audited vulnerabilities. It emitted an ESLint 9 deprecation
  warning; pytest emitted two upstream TestClient deprecation warnings. Checks
  pass; these warnings are not suppressed.

The initial Docker daemon was stopped; the installed OrbStack daemon was started.
The local infrastructure remains running. API and web smoke processes were stopped.
Use `make infra-down` to stop infrastructure while preserving volumes.

## Next step

EPIC-003: introduce SQLAlchemy, Pydantic domain schemas, and Alembic migrations
for the roadmap's initial tables, with FK, uniqueness, tenant-scope, and provenance
checks. Follow with EPIC-005 durable workers and then the gateway/provider slice.
Do not implement the full domain or a fixed agent pipeline in one step.
