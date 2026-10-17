.PHONY: db api web dev schema test check

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

test:
	docker compose run --rm --no-deps api python -m pytest -q
	docker compose run --rm --no-deps web npm test

check:
	docker compose config --quiet
	docker compose run --rm --no-deps web npm run build
