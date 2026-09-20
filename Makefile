.PHONY: install check build api web

install:
	uv sync --all-packages --locked
	npm ci

check:
	uv run --all-packages --locked ruff check .
	uv run --all-packages --locked ruff format --check .
	uv run --all-packages --locked mypy apps/api/src packages tests scripts workers/orchestration/src
	uv run --all-packages --locked pytest
	npm run lint
	npm run typecheck

build:
	uv build --all-packages
	npm run build

api:
	uv run --all-packages --locked uvicorn ranah_api.main:app --reload --host 127.0.0.1

web:
	npm run dev

worker-orchestration:
	uv run --all-packages --locked python -m ranah_worker_orchestration.worker

.PHONY: db-upgrade db-downgrade db-revision
db-upgrade:
	uv run --all-packages --locked alembic -c packages/domain/alembic.ini upgrade head

db-downgrade:
	uv run --all-packages --locked alembic -c packages/domain/alembic.ini downgrade -1

db-revision:
	uv run --all-packages --locked alembic -c packages/domain/alembic.ini revision --autogenerate -m "$(m)"

.PHONY: smoke infra-up infra-down infra-check infra-logs

smoke:
	uv run --all-packages --locked python scripts/smoke.py

infra-up:
	docker compose up -d --wait --wait-timeout 180
	docker compose run --rm minio-init

infra-down:
	docker compose down

infra-check:
	docker compose exec -T postgres psql -U ranah -d ranahresearch -v ON_ERROR_STOP=1 -c "SELECT '[1,2,3]'::vector;"
	docker compose exec -T temporal temporal --address temporal:7233 operator cluster health
	docker compose exec -T temporal temporal --address temporal:7233 --namespace default operator namespace describe
	docker compose run --rm minio-init "sh /checks/s3-check.sh"
	curl --fail --silent --show-error "http://$$(docker compose port temporal-ui 8080)/" > /dev/null

infra-logs:
	docker compose logs --tail 100
