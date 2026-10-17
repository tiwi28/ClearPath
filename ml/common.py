"""Shared paths, column names, and street-name normalization for the ML pipeline."""
import re
from pathlib import Path

# Data lives at the repo root (HTV 11/data), one level above ml/.
ML = Path(__file__).resolve().parent
OUT = ML.parent / "data"
RAW = OUT / "raw"
PROCESSED = OUT / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)
APP_DATA = ML.parent / "backend" / "app" / "data"

# Toronto publishes 311 data monthly (around the 8th, through the end of the previous
# month), so on any day the newest available report can be up to ~40 days old.
# Live-model history features only look at days before t - LAG.
LAG = 40

# 311 columns (after lowercasing/stripping in 01_load_311.py).
C_DATE = "creation date"
C_TYPE = "service request type"
C_ST1 = "intersection street 1"
C_ST2 = "intersection street 2"
C_FSA = "first 3 chars of postal code"
C_WARD = "ward"

# Centreline intersection file (data/raw/geo). No lat/lon columns:
# coordinates are inside a GeoJSON MultiPoint string in G_GEOM.
GEO_FILE = RAW / "geo" / "Centreline Intersection - 4326.csv"
G_DESC = "INTERSECTION_DESC"
G_GEOM = "geometry"

_ABBR = {
    "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR",
    "BOULEVARD": "BLVD", "CRESCENT": "CRES", "COURT": "CRT", "PLACE": "PL",
    "PARKWAY": "PKWY", "TRAIL": "TRL", "CIRCLE": "CIR", "SQUARE": "SQ",
    "GARDENS": "GDNS", "TERRACE": "TER",
    "EAST": "E", "WEST": "W", "NORTH": "N", "SOUTH": "S",
}
_ABBR_RE = re.compile(r"\b(" + "|".join(_ABBR) + r")\b")


def norm(street):
    """Normalize a street name so 311 and centreline spellings match."""
    if not isinstance(street, str):
        return None
    s = street.upper().replace("'", "")       # "SEWELL'S" -> "SEWELLS", not "SEWELL S"
    s = re.sub(r"[^A-Z0-9 ]", " ", s)          # other punctuation -> space
    s = re.sub(r"\bMC\s+", "MC", s)            # "MC FARLAND" -> "MCFARLAND"
    s = _ABBR_RE.sub(lambda m: _ABBR[m.group(1)], s)
    s = " ".join(s.split())
    return s or None


def key(a, b):
    """Order-independent key for an intersection of two normalized streets."""
    if not a or not b:
        return None
    return "|".join(sorted((a, b)))
