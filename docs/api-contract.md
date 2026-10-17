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
