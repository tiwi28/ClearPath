import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from . import barriers, feeds, forecast, hazards, reports, restrictions, risk, routing, ttc, wards
from .schemas import HazardRequest, PlanRequest, PlanResponse, ReportRequest

STATIC_CACHE = "public, max-age=86400"
LIVE_CACHE = "public, max-age=60, stale-while-revalidate=300"
WARM_UP_S = 25


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Keep live feeds and today's forecast warm, so no request waits on a download. Startup waits
    # (up to WARM_UP_S) for the first load, so the API only reports healthy once it is warm.
    if settings.background_refresh:
        primed = feeds.start_refresher([ttc.ALERTS, restrictions.FEED, forecast.WEATHER], after=forecast.predict)
        await asyncio.to_thread(primed.wait, WARM_UP_S)
    yield


app = FastAPI(title="Clearpath Toronto API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/barriers")
def list_barriers(bbox: str | None = None, kind: str | None = None):
    return {"type": "FeatureCollection", "data_source": settings.barrier_source,
            "features": barriers.query_features(barriers.parse_bbox(bbox), kind)}


@app.get("/risk")
def risk_map(day: date | None = None, bbox: str | None = None):
    """Predicted barrier risk for today or up to two days ahead."""
    prediction = forecast.predict(day)
    return {"type": "FeatureCollection", **{key: value for key, value in prediction.items() if key != "features"},
            "features": risk.query_cells(prediction["features"], barriers.parse_bbox(bbox))}


@app.get("/stations")
def stations():
    """TTC rapid-transit stations with elevator access and current elevator/escalator outages."""
    alerts = ttc.live_alerts()
    return {"alerts_available": alerts["available"], "alerts_updated": alerts["updated"],
            "closures": [{key: closure[key] for key in ("line", "from_station", "to_station", "text")}
                         for closure in alerts["closures"]],
            "stations": ttc.station_status()}


@app.get("/geocode")
def geocode(text: str = Query(min_length=2, max_length=200)):
    return {"results": routing.geocode(text)}


@app.post("/plan", response_model=PlanResponse)
def plan(request: PlanRequest):
    return routing.plan(request)


@app.get("/wards")
def ward_list(response: Response):
    response.headers["Cache-Control"] = STATIC_CACHE
    return {"wards": wards.list_wards()}


@app.get("/wards/locate")
def ward_locate(response: Response, lng: float = Query(ge=-180, le=180), lat: float = Query(ge=-90, le=90)):
    response.headers["Cache-Control"] = STATIC_CACHE
    return wards.locate(lng, lat)


@app.get("/wards/{ward_id}")
def ward_card(ward_id: int, request: Request):
    """Report card for one ward: City 311 accessibility reports plus live TTC, closure and forecast numbers."""
    body = json.dumps(wards.card(ward_id), separators=(",", ":")).encode()
    etag = f'W/"{hashlib.sha1(body).hexdigest()[:20]}"'
    headers = {"Cache-Control": LIVE_CACHE, "ETag": etag}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


@app.post("/trip/hazards")
def trip_hazards(request: HazardRequest):
    """What's ahead on a trip, ordered by distance along the route."""
    return {"hazards": hazards.find(request.route.coordinates, request.day,
                                    [stop.model_dump() for stop in request.stations],
                                    [gap.model_dump() for gap in request.unverified])}


@app.post("/reports", status_code=201)
def report(body: ReportRequest, request: Request):
    """A rider's report from a trip: a spot is blocked, or it's clear again."""
    # Behind a proxy or tunnel the first X-Forwarded-For hop is the rider. It can be spoofed, which
    # only loosens this per-address limit; confirmations are still counted per device.
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    address = forwarded or (request.client.host if request.client else "unknown")
    return reports.record(body.device_id, body.kind, body.state, body.profile, *body.location, address=address)
