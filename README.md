# Clearpath Toronto

See where Toronto's accessibility barriers are, route around them, and hold your ward accountable.

> Screenshots and demo GIF go here (add early).

## Quick start

```bash
cp .env.example .env            # fill in GEMINI_API_KEY and ORS_API_KEY
make db                         # Postgres + PostGIS + Timescale
cd backend && python -m venv .venv && . .venv/bin/activate \
  && pip install -r requirements.txt && cd ..
make api                        # http://localhost:8000/docs
cd frontend && npm i && cd .. && make web   # http://localhost:5173
```

The API serves mock JSON from `backend/app/mock/` until real data is wired in,
so frontend and 3D work never blocks on the backend.

## Layout

| Path | What | Deploys to |
|---|---|---|
| `backend/` | FastAPI, ingest, routing, Gemini | Vultr |
| `frontend/` | Vite + React + Tailwind + three.js | Vercel |
| `audit/` | Optional YOLOv8 detector (isolated) | n/a |
| `docs/` | API contract, data limits | n/a |

## Workflow

Trunk-based: `main` always deploys. Branch as `feat/<area>-<thing>`, open a PR, one quick review, squash merge.
