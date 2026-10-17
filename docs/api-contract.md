# Navigation API

Pydantic models in `backend/app/schemas.py` define the contract.
Interactive documentation is available at http://localhost:8000/docs.

## Endpoints

| Endpoint | Response |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `POST /plan` | Typical route, accessible route, TTC options, risk info and warnings |
| `GET /risk?day=&bbox=` | Predicted-risk hexagons (`cell`, `risk`, `reports_last_year`) with `date`, `reports_through`, `weather`, `model` |
| `GET /stations` | TTC stations (`name`, `lines`, `coordinates`, `has_elevator`, live `outages`) and subway `closures` notices |
| `GET /geocode?text=` | `{"results":[{"label","coordinates"}]}` Toronto address suggestions (2-200 chars) |
| `GET /barriers?bbox=&kind=` | GeoJSON FeatureCollection of known barriers with `data_source` |

## Plan request

```json
{
  "from": [-79.3806, 43.6453],
  "to": [-79.3871, 43.6426],
  "profile": "manual_wheelchair",
  "include_transit": true,
  "avoid_risk": true,
  "day": "2026-10-17"
}
```

Coordinates always use `[longitude, latitude]`. Points must be finite, valid and different.
Unknown fields are rejected with HTTP 422.

- `profile`: `manual_wheelchair` (default), `power_wheelchair`, `walker`, `limited_stamina`.
  See `backend/app/profiles.py` for the ORS options, pace and transit rules of each.
- `include_transit` (default `true`): also plan TTC trips with Transitous.
- `avoid_risk` (default `true`): allow a detour around likely sidewalk barriers.
- `day` (default today in Toronto): forecast day for predicted risk, today to two days ahead.

## Plan response

- `ideal`: the typical route (ORS `foot-walking`), or `null`. Includes `stairs`, a list of
  LineStrings where ORS reports steps.
- `accessible`: the profile's route, or `null` when none exists (then `warnings` says why).
  - `geometry`, `distance_m`, `duration_s` (from the profile's pace when it has one), `steps`.
  - `risk`: `max`, length-weighted `mean`, `cells_crossed`, `high_risk_cells` (risk >= 0.3),
    `high_risk_share` (fraction of length in those cells), or `null` if the forecast failed.
  - `unverified`: stretches next to an endpoint that couldn't be confirmed step-free:
    `{end: "start"|"destination", geometry, length_m, uses_stairs}`.
  - `risk_avoided`, `standard`: when a lower-risk detour replaced the route, `standard` is the
    route it replaced.
  - `avoided_barrier_ids`: verified barrier polygons sent to ORS as avoidance areas.
- `transit`: up to 3 options, each with `start`, `end`, `duration_s`, `transfers`, `walk_m`,
  `legs` (`mode`, `line`, `headsign`, `color`, `from_name`, `to_name`, times, `geometry`,
  `risk` for walk legs), `issues` (`severity` `blocker`|`warning`, `station`, `kind`, `text`)
  and `step_free`. Wheelchair profiles never receive options with blockers.
- `risk`: `{available, date, reports_through}`.
- `warnings`: unconfirmed stretches, hidden transit trips, forecast or provider outages, and data limits.

### Routing behaviour

- **Island recovery**: when the profile's ORS route fails (404), the backend retries from
  points 40, 120 and 300 m along the typical route from the destination, then the start,
  then both. It returns the first success with the skipped stretches in `unverified`.
- **Lower-risk detour**: candidates are nearby cells with risk >= 0.1, never cells containing
  an endpoint. The backend avoids the riskiest 50%, 25%, then 10% of them and keeps the first
  detour that is at most 1.5x longer and lowers mean risk by at least 0.03.
- **Transit checks**: each subway/LRT stop is matched to `ttc_stations.json`. A station without
  elevators, or with an elevator outage in the live feed, is a blocker for wheelchair profiles
  and a warning for others. Escalator outages are warnings for walker and stamina profiles. If
  every option is blocked, the backend asks Transitous again for buses and streetcars only.
- Predicted risk never causes an error. Only verified barriers are hard constraints.

## Errors

Application errors use `{"detail":{"code":"...","message":"..."}}`.
Model validation uses FastAPI's standard `detail` array.

| Status | Meaning |
|---|---|
| 422 | Invalid request, unknown profile or field, malformed bbox, or forecast day out of range |
| 404 | No accessible street route and no transit option |
| 409 | The only route crosses a known obstruction |
| 503 | Missing ORS key, unavailable barrier storage, or (on `/risk`) weather forecast unavailable |
| 502 | Provider failure or invalid provider response |
| 504 | Provider timeout |

`/plan` keeps working without the forecast (`risk.available: false`) or without Transitous
(`transit: []`); each case adds a warning.
