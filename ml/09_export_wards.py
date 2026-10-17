"""Export per-ward accessibility report statistics and ward boundaries for the backend.

Ward report cards show City 311 data only. This reads every accessibility report
(sr_access.parquet, all of them, not just the geocoded ones) and the City's 25-ward
boundaries from Toronto Open Data.

Writes (backend/app/data/):
  ward_stats.json  per ward: headline counts, 24 monthly counts by category,
                   the same months a year earlier, top intersections, share still open
  wards.geojson    simplified 25-ward boundaries (EPSG:4326)

Usage (from ml/): python 09_export_wards.py
"""
import json
import re
import urllib.request

import pandas as pd
from shapely.geometry import mapping, shape

from common import APP_DATA, C_DATE, C_ST1, C_ST2, C_TYPE, C_WARD, PROCESSED

WARDS_URL = ("https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/5e7a8234-f805-43ac-820f-03d7c360b588/"
             "resource/737b29e0-8329-4260-b6af-21555ab24f28/download/city-wards-data-4326.geojson")
SIMPLIFY_DEG = 0.00005  # about 5 m: plenty for an outline and point-in-ward lookups
OPEN_STATUSES = {"New", "In Progress", "In-progress", "Initiated"}
MONTHS = 24


def category(request_type: str) -> str:
    """snow_ice: uncleared or icy; ramps: ramps, tactile pavers, ponding; damage: everything else."""
    text = request_type.lower()
    if re.search(r"snow|ice|icy|salt", text):
        return "snow_ice"
    if re.search(r"ramp|tactile|ponding", text):
        return "ramps"
    return "damage"


def ward_id(name: str) -> int | None:
    match = re.search(r"\((\d+)\)\s*$", name or "")
    return int(match.group(1)) if match else None


def last_winter(through: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The most recent complete Nov 1 - Apr 30 winter before `through`."""
    end_year = through.year if through >= pd.Timestamp(through.year, 5, 1) else through.year - 1
    return pd.Timestamp(end_year - 1, 11, 1), pd.Timestamp(end_year, 4, 30)


sr = pd.read_parquet(PROCESSED / "sr_access.parquet", columns=[C_DATE, "day", "status", C_WARD, C_TYPE, C_ST1, C_ST2])
sr["ward_id"] = sr[C_WARD].map(ward_id)
sr = sr.dropna(subset=["ward_id"]).astype({"ward_id": int})
sr["category"] = sr[C_TYPE].map(category)
sr["month"] = sr["day"].dt.to_period("M")

through = sr["day"].max().normalize()
year_ago = through - pd.DateOffset(years=1)
winter_start, winter_end = last_winter(through)
last_month = through.to_period("M")
months = pd.period_range(last_month - (MONTHS - 1), last_month, freq="M")
earlier = months - 12

stats = {}
for wid, group in sr.groupby("ward_id"):
    recent = group[group["day"] > year_ago]
    winter = group[(group["day"] >= winter_start) & (group["day"] <= winter_end)]
    monthly = group.groupby(["month", "category"]).size()

    def series(periods):
        return [{"month": str(p), **{c: int(monthly.get((p, c), 0)) for c in ("snow_ice", "damage", "ramps")}}
                for p in periods]

    corners = recent.dropna(subset=[C_ST1, C_ST2])
    places = (corners[C_ST1].str.title() + " & " + corners[C_ST2].str.title()).value_counts().head(5)
    stats[str(wid)] = {
        "id": wid,
        "name": re.sub(r"\s*\(\d+\)\s*$", "", group[C_WARD].iloc[0]),
        "snow_last_winter": int((winter["category"] == "snow_ice").sum()),
        "damage_12m": int((recent["category"] == "damage").sum()),
        "ramps_12m": int((recent["category"] == "ramps").sum()),
        "reports_12m": int(len(recent)),
        "reports_prior_12m": int(((group["day"] > year_ago - pd.DateOffset(years=1)) & (group["day"] <= year_ago)).sum()),
        "open_share_12m": round(float(recent["status"].isin(OPEN_STATUSES).mean()), 3) if len(recent) else 0.0,
        "monthly": series(months),
        "monthly_prior_year": series(earlier),
        "top_places": [{"place": place, "reports": int(n)} for place, n in places.items()],
    }

meta = {"reports_through": through.date().isoformat(),
        "winter": [winter_start.date().isoformat(), winter_end.date().isoformat()],
        "year_from": (year_ago + pd.Timedelta(days=1)).date().isoformat()}
(APP_DATA / "ward_stats.json").write_text(json.dumps({"meta": meta, "wards": stats}, indent=1))

with urllib.request.urlopen(WARDS_URL, timeout=60) as response:
    raw = json.load(response)
features = []
for feature in raw["features"]:
    props = feature["properties"]
    geometry = shape(feature["geometry"]).simplify(SIMPLIFY_DEG, preserve_topology=True)
    features.append({"type": "Feature", "properties": {"id": int(props["AREA_SHORT_CODE"]), "name": props["AREA_NAME"]},
                     "geometry": json.loads(json.dumps(mapping(geometry)))})
features.sort(key=lambda f: f["properties"]["id"])
(APP_DATA / "wards.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                                     separators=(",", ":")))

print(f"{len(stats)} wards, reports through {meta['reports_through']}, winter {meta['winter']}")
print(f"wards.geojson: {len(features)} boundaries, {(APP_DATA / 'wards.geojson').stat().st_size // 1024} KB")
