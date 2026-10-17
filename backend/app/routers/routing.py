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
