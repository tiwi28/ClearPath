.PHONY: db api web dev schema ingest test

db:
	docker compose up -d db

schema:
	docker compose exec -T db psql -U postgres -d clearpath < backend/sql/schema.sql

api:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

ingest:
	cd backend && . .venv/bin/activate && python -m app.ingest.wards

test:
	cd backend && . .venv/bin/activate && pytest -q
