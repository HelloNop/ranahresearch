# RanahResearch

Repository and local development foundation for the RanahResearch project.

RanahResearch is an agentic scientific research & writing SaaS designed as a
scientific research operating environment.

Core workflow:

Idea
→ Research Planning
→ Protocol
→ Literature Search
→ Screening
→ Evidence Extraction
→ Evidence Synthesis
→ Optional Meta-analysis
→ Manuscript
→ Reviewer Council
→ Revision
→ Author Review

## Documents

1. `docs/PRD.md`
2. `docs/SCIENTIFIC_METHODOLOGY.md`
3. `docs/TECHNICAL_ARCHITECTURE.md`
4. `docs/OPENDRAFT_ADOPTION.md`
5. `docs/DATA_MODEL.md`
6. `docs/AGENT_CONTRACTS.md`
7. `docs/IMPLEMENTATION_ROADMAP.md`
8. `docs/INDEX.md`

OpenDraft is treated as an engineering reference/donor, not as the production
architecture.

## Development foundation

The specifications in [`docs/`](docs/INDEX.md) are the source of truth.
This checkout implements EPIC-001 and the local infrastructure for EPIC-002.
The web page and API `/health` are startup checks, not research features.

Prerequisites: Python 3.12 (managed by uv), [uv](https://docs.astral.sh/uv/),
Node.js 24, npm, Make, and Docker with Compose v2.20+ and a running daemon.
Node 24 satisfies [Next.js requirements](https://nextjs.org/docs/app/getting-started/installation).

```sh
make install             # locked Python workspace + npm workspace
make check               # Ruff, mypy, pytest, ESLint, strict TypeScript
make build               # nine Python wheels/sdists + production Next.js build
make smoke               # real HTTP startup checks; temporary ports 18000/13000
make infra-up            # PostgreSQL/pgvector, Temporal, Temporal UI, S3 + bucket
make infra-check         # database/vector, Temporal namespace, S3, UI checks
make api                 # terminal 1: http://127.0.0.1:8000/docs
make web                 # terminal 2: http://127.0.0.1:3000
```

`make infra-down` stops local infrastructure without removing its volumes.
`make infra-logs` prints recent service logs. API/web are host processes so their
normal development reloaders work; stop them with Ctrl-C.
See [`infra/README.md`](infra/README.md) for connections, persistence, and troubleshooting.

## Repository layout

```text
apps/
  web/                   Next.js + React + strict TypeScript
  api/                   FastAPI entry point (ranah_api)
packages/
  domain/                domain boundaries (ranah_domain)
  agents/                future bounded agent runtime
  llm/                   future provider-neutral LLM gateway
  literature/            future academic provider adapters
  evidence/              future evidence extraction/validation
  review/                future structured review issues
  statistics/            future deterministic Python computation
  documents/             future citation/export rendering
workers/
  orchestration/         durable workflow entry points (EPIC-005)
  research/
  document/
  statistics/
prompts/                 versioned prompts as agents are introduced
tests/                   executable foundation checks
scripts/                 HTTP smoke check
evals/                  scientific benchmarks as components are introduced
docs/                   product/scientific/technical source of truth
infra/                  local development infrastructure
```

Python uses a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
with one `uv.lock`; run commands from the repository root with
`uv run --all-packages --locked ...`. Packages use `src/ranah_*` names, avoiding
collisions with the standard library's `statistics`. No business dependencies
are added until needed. The npm workspace has one root `package-lock.json`.
Commit both lockfiles. Workers are intentional directory placeholders until
EPIC-005, not fake runnable workers.

## Architecture boundaries

- Modular monolith with durable Temporal workers; PostgreSQL is canonical
  scientific state, pgvector provides initial retrieval, S3 stores binary artifacts.
- `WorkRecord`, `Study`, `Evidence`, `Claim`, and `Manuscript` remain distinct concepts.
- OpenAI will be the initial provider behind the LLM gateway. OpenAlex, Crossref,
  and Semantic Scholar will be reached through academic adapters.
- Meta-analysis computation is deterministic Python, never LLM arithmetic.
- No `DraftContext`, fixed 19-agent pipeline, filesystem/checkpoint JSON state,
  microservices, Kubernetes, or dedicated vector database.
- OpenDraft is a selective donor only. No code is adapted yet; see
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) before adapting substantial code.

## Branch and contribution strategy

Use `main` as the integration branch and short-lived branches such as
`epic-003/core-domain`. Open a bounded PR referencing its epic, update relevant
docs/migrations, and pass CI before merging. Configure required checks and branch
protection when a remote is connected; local Git initialization cannot enforce them.
No remote or initial commit is created automatically.

Follow the roadmap: EPIC-003 next, then EPIC-005/006/008 and selective adoption.
For deterministic behavior, write the failing check first. Add scientific golden
fixtures/evals when scientific components exist. Foundation CI runs checks,
builds, HTTP smoke tests, and infrastructure integration checks.

Implementation inventory, acceptance results, and remaining limitations:
[`docs/FOUNDATION_STATUS.md`](docs/FOUNDATION_STATUS.md).
