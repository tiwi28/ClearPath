"""Build backend/app/data/ttc_stations.json: TTC rapid-transit stations and whether they have elevators.

Stations, lines and coordinates come from TTC's GTFS (Toronto Open Data, "TTC Routes and
Schedules"). GTFS marks nearly every stop wheelchair_boarding=1, so elevator access comes
from TTC's Elevators and Escalators page instead (ELEVATOR_STATIONS below). Lines 5 and 6
are new LRT lines built fully accessible.

Usage (from backend/): python scripts/build_ttc_stations.py
"""

import csv
import io
import json
import re
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id=ttc-routes-and-schedules"
ELEVATORS_URL = "https://www.ttc.ca/accessibility/Easier-access-on-the-TTC/Elevators-and-Escalators"
# Stations listed with elevators on ELEVATORS_URL (checked 2026-10-17).
ELEVATOR_STATIONS = {
    "1": ["Vaughan Metropolitan Centre", "Highway 407", "Pioneer Village", "York University", "Finch West",
          "Downsview Park", "Sheppard West", "Wilson", "Yorkdale", "Lawrence West", "Glencairn", "Cedarvale",
          "St Clair West", "Dupont", "Spadina", "St George", "Queen's Park", "St Patrick", "Osgoode",
          "St Andrew", "Union", "Queen", "TMU", "Wellesley", "Bloor-Yonge", "Rosedale", "Summerhill",
          "St Clair", "Davisville", "Eglinton", "Lawrence", "York Mills", "Sheppard-Yonge",
          "North York Centre", "Finch"],
    "2": ["Kipling", "Royal York", "Jane", "Runnymede", "High Park", "Keele", "Dundas West", "Lansdowne",
          "Dufferin", "Ossington", "Christie", "Bathurst", "Spadina", "St George", "Bay", "Bloor-Yonge",
          "Sherbourne", "Castle Frank", "Broadview", "Chester", "Pape", "Donlands", "Greenwood", "Coxwell",
          "Woodbine", "Main Street", "Victoria Park", "Warden", "Kennedy"],
    "4": ["Sheppard-Yonge", "Bayview", "Bessarion", "Leslie", "Don Mills"],
}
FULLY_ACCESSIBLE_LINES = {"5", "6"}
LINES = {"1", "2", "4", "5", "6"}
ALIASES = {"bloor": "Bloor-Yonge", "yonge": "Bloor-Yonge"}  # one interchange, two GTFS names


def station_name(stop_name: str) -> str:
    """'Union Station - Northbound Platform Towards Finch' -> 'Union'."""
    base = re.split(r" - | Station\b", stop_name)[0].strip()
    return ALIASES.get(base.lower(), base)


def main():
    package = json.load(urllib.request.urlopen(CKAN, timeout=60))["result"]
    url = next(resource["url"] for resource in package["resources"] if resource["url"].endswith(".zip"))
    archive = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=300).read()))

    def read(name):
        return csv.DictReader(io.TextIOWrapper(archive.open(name), "utf-8-sig"))

    routes = {row["route_id"]: row["route_short_name"] for row in read("routes.txt")
              if row["route_short_name"] in LINES and row["route_type"] in ("0", "1")}
    trips = {row["trip_id"]: routes[row["route_id"]] for row in read("trips.txt") if row["route_id"] in routes}
    stop_lines = defaultdict(set)
    for row in read("stop_times.txt"):
        if row["trip_id"] in trips:
            stop_lines[row["stop_id"]].add(trips[row["trip_id"]])

    stations = defaultdict(lambda: {"lines": set(), "points": []})
    for stop in read("stops.txt"):
        if stop["stop_id"] in stop_lines:
            station = stations[station_name(stop["stop_name"])]
            station["lines"] |= stop_lines[stop["stop_id"]]
            station["points"].append((float(stop["stop_lon"]), float(stop["stop_lat"])))

    listed = {name for names in ELEVATOR_STATIONS.values() for name in names}
    output = []
    for name, station in sorted(stations.items()):
        lines = sorted(station["lines"])
        subway = [line for line in lines if line not in FULLY_ACCESSIBLE_LINES]
        has_elevator = name in listed if subway else True
        longitude = sum(point[0] for point in station["points"]) / len(station["points"])
        latitude = sum(point[1] for point in station["points"]) / len(station["points"])
        output.append({"name": name, "lines": lines, "coordinates": [round(longitude, 6), round(latitude, 6)],
                       "has_elevator": has_elevator})
    unknown = listed - set(stations)
    if unknown:
        raise SystemExit(f"Elevator list names not found in GTFS: {sorted(unknown)}")

    path = Path(__file__).resolve().parents[1] / "app" / "data" / "ttc_stations.json"
    path.write_text(json.dumps({
        "sources": {"stations": url, "elevators": ELEVATORS_URL}, "built": date.today().isoformat(),
        "stations": output,
    }, indent=1) + "\n")
    print(f"{len(output)} stations, {sum(not s['has_elevator'] for s in output)} without elevators:",
          ", ".join(s["name"] for s in output if not s["has_elevator"]))


if __name__ == "__main__":
    main()
