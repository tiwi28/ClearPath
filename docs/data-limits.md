# Data limits

- Default barrier fixtures are fictional. Their URLs identify source organizations, not real reports at those locations.
- ORS wheelchair routes depend on underlying map connectivity and accessibility tags. A route is not a guarantee of an accessible trip.
- Only open, verified blockers with valid polygon footprints affect routing. A reported point does not establish an obstruction's extent.
- 311 reports are self-reported. Missing reports do not establish that a path has no barriers.
- Only 311 requests with an intersection (two street names) can be placed on the map: about 30% of accessibility requests. Address-based requests only give a 3-character postal prefix. Damaged-sidewalk reports have street names far less often (~14%) than snow/ice reports (~40-60%), so the risk model leans toward winter barriers.
- Postgres starts without imported city records. This prototype contains no live ingestion.
- Predicted risk is forecast for today and the next two days from 311 reports older than 40 days (Toronto publishes monthly) and the Open-Meteo forecast. It estimates the chance of an accessibility 311 report per ~0.7 km² cell, which is coarser than a single sidewalk, and it is never treated as a confirmed barrier. Cells with fewer than 3 past reports have no prediction.
- Weather comes from one airport location and is applied city-wide. Forecast weather differs from the observed station data the model was trained on.
- A stretch marked "not confirmed" is where ORS couldn't find a step-free connection near an endpoint, often because OpenStreetMap lacks ramp or elevator data there. It may still be accessible.
- TTC station elevator access comes from TTC's published list (checked 2026-10-17). Live outages come from TTC's alerts feed, which can lag. Transitous trip times are schedules unless marked real-time.
- Transitous is a free community service with no uptime guarantee. If it is down, only street routes are shown.
- ORS travel times are estimates and do not reflect every person's mobility speed.
