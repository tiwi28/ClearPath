# ClearPath Toronto

Toronto trip planning for people who use wheelchairs, walkers or canes, or have
limited stamina. It compares the typical route most map apps suggest with an
accessible one. It checks TTC station elevators against live outages and steers
around sidewalks a model predicts are likely to be blocked today.

## Run with Docker

Put `ORS_API_KEY=your-key` in the root `.env` file, then run:

```bash
docker compose up --build
```

Open http://localhost:5173. API documentation is at http://localhost:8000/docs.
If port 5173 is occupied, use `WEB_PORT=5174 docker compose up --build` and open
http://localhost:5174. Set `WEB_PORT` in `.env` to retain that choice.

Docker runs the frontend, FastAPI, and Postgres/PostGIS. Application source is
mounted for hot reload (Vite polls for changes inside Docker). Rebuild after
dependency changes. Changing `.env` needs `docker compose up -d api` so the API
container receives the new values.

## Plan a trip

1. **Where are you going?** Search From and To (ORS address search within Toronto),
   use your location, paste `longitude, latitude`, or click the map.
   **Try an example** fills Union Station to the CN Tower.
2. **How do you get around?** Manual wheelchair, power wheelchair or scooter,
   walker/cane/crutches, or limited stamina. Each sets ORS slope and curb limits,
   walking pace, and transit rules (see `backend/app/profiles.py`). The choice is
   remembered in the browser. Toggles: include the TTC, avoid likely sidewalk barriers.
3. **Your options.** Each option is a card. Selecting one draws it on the map.
   - **Accessible route**: the profile's street route, which avoids stairs. It
     says what it avoids compared with the typical route ("Avoids 2 sets of stairs").
   - **TTC options** from Transitous. Every subway/LRT station on the trip is checked
     against TTC's elevator list and live elevator/escalator outages. Wheelchair profiles
     never get a trip through a station without a working elevator: those trips are
     hidden, and buses/streetcars are offered instead.
   - **Typical route**: ORS foot-walking, what most map apps suggest. It is always drawn
     dashed, with its stairs in red.

**Routes that used to fail.** ORS's wheelchair profile snaps each endpoint to its nearest
path. Near PATH, Union Station, the CN Tower or park paths, that path may only connect to
the street by stairs, so ORS returned "no route". The backend now walks in along the typical
route (40/120/300 m from the failing end) until a route without stairs exists. It marks the
remaining stretch as **not confirmed** (dotted orange) instead of failing.

**Map layers** (top left): sidewalk barrier forecast (hexagons), TTC station elevators
(green icon: working, red icon: out, grey icon: no elevator), known barriers, and the forecast day (today or
the next two days). Point at a hexagon or station for details.

**Debugging:** API requests and responses are in the browser's network tab. Server
tracebacks: `docker compose logs -f api`.

## Live data sources

| Data | Source | Refresh |
|---|---|---|
| Barrier forecast | `ml/` live LightGBM model + Open-Meteo forecast (Toronto Pearson) | Weather hourly; 311 history monthly with `ml/08_refresh_311.py` |
| Street routes, address search | OpenRouteService (`ORS_API_KEY`) | Per request, cached 5 min |
| TTC trips | Transitous (MOTIS) public API, TTC GTFS | Per request |
| Station elevators | `backend/app/data/ttc_stations.json` from TTC GTFS + TTC's elevator page | `python backend/scripts/build_ttc_stations.py` when TTC adds elevators |
| Elevator/escalator outages, subway notices | `alerts.ttc.ca` live alerts | Cached 2 min |

Predicted risk is advisory: it is the chance of an accessibility 311 report in the next
3 days, not a confirmed barrier. Only verified barrier polygons are hard constraints.
See `ml/README.md` for how the live model only uses data that exists today.

## Backend layout

```text
backend/app/
  main.py           FastAPI app, CORS, and the HTTP endpoints
  schemas.py        Pydantic request and response validation
  profiles.py       Mobility profiles -> ORS options, pace, Transitous settings
  routing.py        Trip plan: typical + accessible routes, island recovery, lower-risk detours
  transit.py        Transitous trips checked against station elevators and outages
  ttc.py            TTC station list and live alerts feed
  forecast.py       Live barrier-risk forecast (LightGBM + Open-Meteo)
  risk.py           Route scoring and avoidance candidates for predicted risk
  barriers.py       Fixture/PostGIS reads, spatial filters, and blocker selection
  config.py         Environment settings
  data/             barriers.json, ttc_stations.json, model and 311 history from ml/07_export.py
```

For a trip, FastAPI validates the JSON with `PlanRequest`. `routing.plan()` loads
today's forecast, starts the transit search in the background, and requests the typical
route (with stairs from ORS waytypes). It then requests the profile's accessible route
(recovering from snapping islands, avoiding verified barriers, and optionally likely
barriers) and returns a `PlanResponse`.

These application endpoints exist:

- `GET /health`
- `GET /barriers?bbox=west,south,east,north&kind=...`
- `GET /risk?day=YYYY-MM-DD&bbox=...`
- `GET /stations`
- `GET /geocode?text=...`
- `POST /plan`

See [the API contract](docs/api-contract.md) for examples and errors.

## Barrier storage

`BARRIER_SOURCE=fixtures` is the default and needs no imported city data.
`BARRIER_SOURCE=postgres` queries imported records from PostGIS. The database
starts empty; there is no ingestion pipeline in this prototype.

Only open, verified records with `blocks_route=true` and valid polygon geometry
affect routing. Reported points remain informational. `geom` stores a record's
point location; `avoidance_geom` stores a precise obstruction footprint when known.

For an existing database volume, run `make schema` to apply the additive schema
changes. Existing records are retained. The legacy `wards` table and `ward_id`
are geographic metadata, not a reporting API. Existing unused database tables
are not dropped when application features are removed.

## Checks

```bash
make test     # Backend and frontend tests in Docker; no real ORS, Transitous, TTC or weather calls
make check    # Compose validation and frontend production build
```

Local development is also available through `make db`, `make api`, and `make web`
after installing Python requirements into `backend/.venv` and running `npm ci`
inside `frontend/`. Vite proxies `/api` to the backend; inside Docker the target
is `http://api:8000`.

API keys stay in ignored `.env` or environment variables, never source defaults
or frontend variables. See [data limits](docs/data-limits.md) before treating
routes or barrier records as real accessibility information.
