from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .geo import TORONTO_BBOX
from .profiles import ProfileName

Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
LngLat = tuple[Longitude, Latitude]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class PlanRequest(BaseModel):
    from_: LngLat = Field(alias="from")
    to: LngLat
    profile: ProfileName = "manual_wheelchair"
    include_transit: bool = True
    avoid_risk: bool = True
    day: date | None = None  # forecast day for predicted risk; defaults to today in Toronto

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def different_endpoints(self):
        if self.from_ == self.to:
            raise ValueError("Choose different start and destination points.")
        return self


class RouteGeometry(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[LngLat] = Field(min_length=2)


class Step(BaseModel):
    instruction: str
    distance_m: NonNegative
    # Indices into the route's coordinates that this step covers, and ORS's turn type
    # (0 left, 1 right, 6 straight, 10 arrive, 11 depart, ...), for turn-by-turn trips.
    way_points: tuple[int, int] | None = None
    type: int | None = None


class RouteRisk(BaseModel):
    max: NonNegative
    mean: NonNegative
    cells_crossed: int
    high_risk_cells: int
    high_risk_share: NonNegative


class Gap(BaseModel):
    """Part of the trip, next to one endpoint, that couldn't be confirmed free of stairs."""
    end: Literal["start", "destination"]
    geometry: RouteGeometry
    length_m: NonNegative
    uses_stairs: bool


class RouteOption(BaseModel):
    geometry: RouteGeometry
    distance_m: NonNegative
    duration_s: NonNegative
    steps: list[Step]
    risk: RouteRisk | None
    stairs: list[RouteGeometry] = []
    unverified: list[Gap] = []


class AccessibleRoute(RouteOption):
    risk_avoided: bool
    standard: RouteOption | None  # the profile's route before a lower-risk detour replaced it
    avoided_barrier_ids: list[int]


class TransitIssue(BaseModel):
    severity: Literal["blocker", "warning"]
    station: str
    kind: str
    text: str


class TransitLeg(BaseModel):
    mode: str
    line: str | None
    headsign: str | None
    color: str | None
    from_name: str
    to_name: str
    start: str
    end: str
    duration_s: NonNegative
    distance_m: NonNegative
    geometry: RouteGeometry | None
    risk: RouteRisk | None


class TransitOption(BaseModel):
    start: str
    end: str
    duration_s: NonNegative
    transfers: int
    walk_m: NonNegative
    legs: list[TransitLeg]
    issues: list[TransitIssue]
    step_free: bool


class RiskInfo(BaseModel):
    available: bool
    date: str | None
    reports_through: str | None


class PlanResponse(BaseModel):
    profile: ProfileName
    ideal: RouteOption | None
    accessible: AccessibleRoute | None
    transit: list[TransitOption]
    risk: RiskInfo
    warnings: list[str]
    barrier_source: Literal["fixtures", "postgres"]


class TripStation(BaseModel):
    name: str
    at_m: NonNegative


class HazardRequest(BaseModel):
    route: RouteGeometry
    day: date | None = None
    stations: list[TripStation] = []
    unverified: list[Gap] = []

    model_config = {"extra": "forbid"}


class ReportRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    kind: Literal["blocked_sidewalk", "snow_ice", "construction", "elevator_out", "other"]
    state: Literal["blocked", "clear"]
    profile: ProfileName | None = None
    location: LngLat

    model_config = {"extra": "forbid"}

    @field_validator("location")
    @classmethod
    def in_toronto(cls, value):
        west, south, east, north = TORONTO_BBOX
        if not (west <= value[0] <= east and south <= value[1] <= north):
            raise ValueError("Reports must be inside Toronto.")
        return value
