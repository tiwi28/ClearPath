.PHONY: db api web dev schema test check ward-summaries

dev:
	docker compose up --build

db:
	docker compose up -d db

schema:
	docker compose exec -T db psql -U postgres -d clearpath < backend/sql/schema.sql

api:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

# Rewrite the AI ward summaries whose numbers changed. Run after ml/09_export_wards.py.
ward-summaries:
	docker compose exec -T api python -m app.write_summaries

test:
	docker compose run --rm --no-deps api python -m pytest -q
	docker compose run --rm --no-deps web npm test

check:
	docker compose config --quiet
	docker compose run --rm --no-deps web npm run build
