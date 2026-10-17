from typing import Literal

from pydantic import BaseModel, Field

Profile = Literal["wheelchair", "walker", "low_vision", "stroller"]
LngLat = tuple[float, float]


class RouteRequest(BaseModel):
    from_: LngLat = Field(alias="from")
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
