"""How each mobility profile maps onto ORS street routing and Transitous transit routing."""

from dataclasses import dataclass, field
from typing import Literal

ProfileName = Literal["manual_wheelchair", "power_wheelchair", "walker", "limited_stamina"]


@dataclass(frozen=True)
class Profile:
    label: str
    ors_profile: Literal["wheelchair", "foot-walking"]
    ors_options: dict = field(default_factory=dict)
    ors_preference: Literal["recommended", "shortest"] = "recommended"
    speed_mps: float | None = None  # None keeps ORS's own duration estimate
    step_free_stations: bool = True  # transit stations must have working elevators
    transit: dict = field(default_factory=dict)


PROFILES: dict[str, Profile] = {
    "manual_wheelchair": Profile(
        label="Manual wheelchair", ors_profile="wheelchair",
        ors_options={"avoid_features": ["steps"],
                     "profile_params": {"restrictions": {"maximum_incline": 6, "maximum_sloped_kerb": 0.06}}},
        transit={"pedestrianProfile": "WHEELCHAIR"},
    ),
    "power_wheelchair": Profile(
        label="Power wheelchair or scooter", ors_profile="wheelchair",
        ors_options={"avoid_features": ["steps"],
                     "profile_params": {"restrictions": {"maximum_incline": 8, "maximum_sloped_kerb": 0.06}}},
        transit={"pedestrianProfile": "WHEELCHAIR"},
    ),
    "walker": Profile(
        label="Walker, cane or crutches", ors_profile="foot-walking",
        ors_options={"avoid_features": ["steps"]}, speed_mps=0.9, step_free_stations=False,
        transit={"pedestrianProfile": "FOOT", "pedestrianSpeed": 0.9},
    ),
    "limited_stamina": Profile(
        label="Limited stamina", ors_profile="foot-walking", ors_preference="shortest",
        ors_options={"avoid_features": ["steps"]}, speed_mps=0.8, step_free_stations=False,
        transit={"pedestrianProfile": "FOOT", "pedestrianSpeed": 0.8, "maxTransfers": 1,
                 "maxPreTransitTime": 600, "maxPostTransitTime": 600},
    ),
}
