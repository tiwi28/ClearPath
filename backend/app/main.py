from datetime import date

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from . import barriers, forecast, risk, routing, ttc
from .schemas import PlanRequest, PlanResponse

app = FastAPI(title="Clearpath Toronto API")

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
