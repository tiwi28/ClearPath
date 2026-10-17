#!/usr/bin/env bash
# Clearpath Toronto: monorepo bootstrap
# Usage:  bash bootstrap.sh            (full, includes Vite frontend)
#         SKIP_FRONTEND=1 bash bootstrap.sh   (skip npm steps)
set -euo pipefail

ROOT="clearpath-toronto"
mkdir -p "$ROOT" && cd "$ROOT"
git init -q 2>/dev/null || true

# ---------- directories ----------
mkdir -p docs \
  backend/app/{routers,services,ingest,mock} backend/sql backend/tests \
  frontend \
  audit \
  data/fixtures \
  .github/workflows

touch backend/app/__init__.py backend/app/routers/__init__.py \
      backend/app/services/__init__.py backend/app/ingest/__init__.py \
      data/fixtures/.gitkeep

# ---------- root files ----------
cat > .gitignore <<'EOF'
# env + secrets
.env
*.pem

# python
.venv/
__pycache__/
*.pyc
.pytest_cache/

# node
node_modules/
dist/

# data: raw downloads ignored, small fixtures committed
data/*
!data/fixtures/
!data/fixtures/**

# audit model weights / videos
audit/*.pt
audit/*.mp4

.DS_Store
EOF

cat > .env.example <<'EOF'
DATABASE_URL=postgresql://postgres:clearpath@localhost:5432/clearpath
GEMINI_API_KEY=
ORS_API_KEY=
FRONTEND_ORIGIN=http://localhost:5173
VITE_API_URL=http://localhost:8000
EOF

cat > docker-compose.yml <<'EOF'
services:
  db:
    image: timescale/timescaledb-ha:pg16   # PostGIS + TimescaleDB
    environment:
      POSTGRES_PASSWORD: clearpath
      POSTGRES_DB: clearpath
    ports: ["5432:5432"]
    volumes:
      - pgdata:/home/postgres/pgdata/data
      - ./backend/sql/schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
volumes:
  pgdata:
EOF

cat > Makefile <<'EOF'
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
EOF

cat > README.md <<'EOF'
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
EOF

# ---------- docs ----------
cat > docs/api-contract.md <<'EOF'
# API contract

Mock responses live in `backend/app/mock/`. Pydantic models in `backend/app/schemas.py` are the source of truth.
Change a shape = update the mock + schema + this file in the same PR.

| Endpoint | Returns | Mock |
|---|---|---|
| `GET /health` | `{status}` | n/a |
| `GET /barriers?bbox=&kind=` | GeoJSON FeatureCollection | `barriers.json` |
| `POST /route` `{from, to, profile}` | geometry, steps[], avoided[], explanation | `route.json` |
| `GET /wards/{id}/report` | stats[], briefing, sources[] | `ward_report.json` |
| `POST /stations/{id}/elevator` `{status}` | station + rerouted flag | `station.json` |
| `POST /audit` | detections[] | `audit.json` |

Profiles: `wheelchair`, `walker`, `low_vision`, `stroller`.
Coordinates are `[lng, lat]` (GeoJSON order) everywhere.
EOF

cat > docs/data-limits.md <<'EOF'
# Data limits (feeds the closing demo slide)

Add a line every time you find a gap. Be specific: what's missing, lagged, or self-reported.

- 311 requests are self-reported: absence of a request is not absence of a barrier.
- (TTC elevator feed: record what you find here on day one.)
- (Ward boundaries: 25-ward model since 2018.)
EOF

# ---------- backend ----------
cat > backend/requirements.txt <<'EOF'
fastapi
uvicorn[standard]
psycopg[binary,pool]
pydantic-settings
httpx
google-genai
geopandas
shapely
pandas
pytest
EOF

cat > backend/Dockerfile <<'EOF'
FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

cat > backend/app/config.py <<'EOF'
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    database_url: str = "postgresql://postgres:clearpath@localhost:5432/clearpath"
    gemini_api_key: str = ""
    ors_api_key: str = ""
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
EOF

cat > backend/app/db.py <<'EOF'
from psycopg_pool import ConnectionPool

from .config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Lazy pool so the API still boots (on mocks) without a database."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.database_url, min_size=1, max_size=5, open=True)
    return _pool
EOF

cat > backend/app/schemas.py <<'EOF'
from typing import Literal

from pydantic import BaseModel

Profile = Literal["wheelchair", "walker", "low_vision", "stroller"]
LngLat = tuple[float, float]


class RouteRequest(BaseModel):
    from_: LngLat
    to: LngLat
    profile: Profile

    model_config = {"populate_by_name": True}


class Step(BaseModel):
    instruction: str
    distance_m: float


class RouteResponse(BaseModel):
    geometry: dict          # GeoJSON LineString
    steps: list[Step]
    avoided: list[dict]     # barriers routed around
    explanation: str        # Gemini plain-language summary


class Stat(BaseModel):
    metric: str
    value: float | int | str
    source_url: str


class WardReport(BaseModel):
    ward_id: int
    name: str
    stats: list[Stat]
    briefing: str
    sources: list[str]


class ElevatorUpdate(BaseModel):
    status: Literal["in_service", "out_of_service"]
EOF

cat > backend/app/mock.py <<'EOF'
import json
from pathlib import Path

MOCK_DIR = Path(__file__).parent / "mock"


def load(name: str) -> dict:
    return json.loads((MOCK_DIR / name).read_text())
EOF

cat > backend/app/main.py <<'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import audit, barriers, routing, wards

app = FastAPI(title="Clearpath Toronto API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(barriers.router)
app.include_router(routing.router)
app.include_router(wards.router)
app.include_router(audit.router)


@app.get("/health")
def health():
    return {"status": "ok"}
EOF

cat > backend/app/routers/barriers.py <<'EOF'
from fastapi import APIRouter

from ..mock import load

router = APIRouter(tags=["barriers"])


@router.get("/barriers")
def list_barriers(bbox: str | None = None, kind: str | None = None):
    # TODO: query Postgres (ST_Intersects on bbox), filter by kind.
    return load("barriers.json")
EOF

cat > backend/app/routers/routing.py <<'EOF'
from fastapi import APIRouter

from ..mock import load
from ..schemas import ElevatorUpdate, RouteRequest

router = APIRouter(tags=["routing"])


@router.post("/route")
def route(req: RouteRequest):
    # TODO: build avoid_polygons from barriers, call ORS, explain via Gemini.
    return load("route.json")


@router.post("/stations/{station_id}/elevator")
def set_elevator(station_id: str, body: ElevatorUpdate):
    # TODO: update stations table; frontend then re-requests /route.
    data = load("station.json")
    data["id"] = station_id
    data["elevator_status"] = body.status
    return data
EOF

cat > backend/app/routers/wards.py <<'EOF'
from fastapi import APIRouter

from ..mock import load

router = APIRouter(tags=["wards"])


@router.get("/wards/{ward_id}/report")
def ward_report(ward_id: int):
    # TODO: compute stats in SQL, pass {metric,value,source_url} rows to Gemini,
    # then validate every number in the briefing appears in the input.
    data = load("ward_report.json")
    data["ward_id"] = ward_id
    return data
EOF

cat > backend/app/routers/audit.py <<'EOF'
from fastapi import APIRouter

from ..mock import load

router = APIRouter(tags=["audit"])


@router.post("/audit")
def audit():
    # Optional add-on. Keep YOLO imports out of the backend path.
    return load("audit.json")
EOF

for f in ors gemini scoring; do
  echo "# TODO: $f service" > "backend/app/services/$f.py"
done
for f in 311 road_restrictions ttc_elevators; do
  echo "# TODO: ingest $f" > "backend/app/ingest/${f}.py"
done
cat > backend/app/ingest/wards.py <<'EOF'
# TODO: download the 25-ward boundaries from Toronto Open Data (CKAN)
# and load into the wards table. First ingest to get working.
EOF

cat > backend/sql/schema.sql <<'EOF'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS wards (
  ward_id int PRIMARY KEY,
  name text,
  geom geometry(MultiPolygon, 4326)
);

CREATE TABLE IF NOT EXISTS barriers (
  id bigserial,
  source text,          -- '311' | 'road_restriction' | 'elevator' | 'audit'
  kind text,            -- 'sidewalk' | 'closure' | 'elevator_out' | 'curb'
  status text,
  opened_at timestamptz NOT NULL,
  closed_at timestamptz,
  ward_id int REFERENCES wards,
  geom geometry(Point, 4326),
  source_url text,
  raw jsonb
);
SELECT create_hypertable('barriers', 'opened_at', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS barriers_geom_idx ON barriers USING gist (geom);

CREATE TABLE IF NOT EXISTS stations (
  id text PRIMARY KEY,
  name text,
  ward_id int,
  has_elevator bool,
  elevator_status text,
  geom geometry(Point, 4326)
);
EOF

cat > backend/tests/test_health.py <<'EOF'
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_barriers_mock_shape():
    body = client.get("/barriers").json()
    assert body["type"] == "FeatureCollection"
EOF

# ---------- mock JSON ----------
cat > backend/app/mock/barriers.json <<'EOF'
{
  "type": "FeatureCollection",
  "features": [
    {"type": "Feature",
     "geometry": {"type": "Point", "coordinates": [-79.2575, 43.7731]},
     "properties": {"id": 1, "source": "311", "kind": "sidewalk", "status": "open",
                    "opened_at": "2026-08-01T12:00:00Z", "ward_id": 24,
                    "source_url": "https://open.toronto.ca/"}},
    {"type": "Feature",
     "geometry": {"type": "Point", "coordinates": [-79.3832, 43.6532]},
     "properties": {"id": 2, "source": "elevator", "kind": "elevator_out", "status": "open",
                    "opened_at": "2026-10-10T08:00:00Z", "ward_id": 13,
                    "source_url": "https://www.ttc.ca/"}}
  ]
}
EOF

cat > backend/app/mock/route.json <<'EOF'
{
  "geometry": {"type": "LineString",
               "coordinates": [[-79.3832, 43.6532], [-79.3800, 43.6560], [-79.3770, 43.6590]]},
  "steps": [
    {"instruction": "Head north on Yonge Street for 300 metres.", "distance_m": 300},
    {"instruction": "Turn right and arrive at the station's step-free entrance.", "distance_m": 80}
  ],
  "avoided": [{"id": 2, "kind": "closure", "reason": "Sidewalk closed for construction"}],
  "explanation": "This route avoids a sidewalk closure and ends at an entrance with a working elevator."
}
EOF

cat > backend/app/mock/ward_report.json <<'EOF'
{
  "ward_id": 24,
  "name": "Scarborough Guildwood",
  "stats": [
    {"metric": "open_sidewalk_requests", "value": 312, "source_url": "https://open.toronto.ca/"},
    {"metric": "median_fix_days", "value": 41, "source_url": "https://open.toronto.ca/"}
  ],
  "briefing": "MOCK: 312 sidewalk requests are open and the median fix takes 41 days.",
  "sources": ["https://open.toronto.ca/"]
}
EOF

cat > backend/app/mock/station.json <<'EOF'
{"id": "union", "name": "Union", "has_elevator": true, "elevator_status": "out_of_service", "rerouted": true}
EOF

cat > backend/app/mock/audit.json <<'EOF'
{"detections": [{"label": "blocked_curb_cut", "confidence": 0.87, "lat": 43.65, "lng": -79.38}]}
EOF

# ---------- audit (isolated) ----------
cat > audit/README.md <<'EOF'
# Audit (optional YOLOv8 add-on)

Fully separate from `backend/`. If this breaks, nothing else notices.
Own requirements, own venv. Output: JSON detections the backend can import via `POST /audit`.
EOF
cat > audit/requirements.txt <<'EOF'
ultralytics
opencv-python
EOF
echo "# TODO: run YOLOv8 on video frames, emit detections as JSON" > audit/detect.py

# ---------- CI ----------
cat > .github/workflows/ci.yml <<'EOF'
name: ci
on: [pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r backend/requirements.txt
      - run: cd backend && pytest -q
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: cd frontend && npm ci && npm run build
EOF

# ---------- frontend ----------
if [ -z "${SKIP_FRONTEND:-}" ]; then
  rmdir frontend 2>/dev/null || true
  npm create vite@latest frontend -- --template react-ts
  (cd frontend && npm i && npm i three @react-three/fiber @react-three/drei maplibre-gl react-map-gl \
     && npm i -D tailwindcss @tailwindcss/vite)

  cat > frontend/vite.config.ts <<'EOF'
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({ plugins: [react(), tailwindcss()] });
EOF
  echo '@import "tailwindcss";' > frontend/src/index.css
fi

mkdir -p frontend/src/{api,components,views,three}
for d in api components views three; do touch "frontend/src/$d/.gitkeep"; done
cp .env.example frontend/.env.example 2>/dev/null || true

# ---------- python venv + first commit ----------
if [ -z "${SKIP_VENV:-}" ]; then
  (cd backend && python3 -m venv .venv && . .venv/bin/activate \
     && pip install -q -r requirements.txt)
fi

git add -A
git commit -qm "chore: scaffold clearpath-toronto monorepo" || true
echo
echo "Done. Next:"
echo "  1. cd $ROOT && cp .env.example .env"
echo "  2. gh repo create clearpath-toronto --private --source=. --push"
echo "  3. make db && make api   (http://localhost:8000/docs)"
