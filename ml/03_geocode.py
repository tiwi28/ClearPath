"""Geocode 311 requests by matching their two intersection streets to the city centreline."""
import json
from itertools import combinations

import pandas as pd

from common import C_ST1, C_ST2, G_DESC, G_GEOM, GEO_FILE, PROCESSED, key, norm

# --- Build the intersection lookup: key(street_a, street_b) -> mean lat/lon ---
geo = pd.read_csv(GEO_FILE, usecols=[G_DESC, G_GEOM], dtype=str)
geo = geo.dropna()
# geometry is a GeoJSON MultiPoint string; the first point is the intersection.
pts = geo[G_GEOM].map(lambda g: json.loads(g)["coordinates"][0])
geo["lon"] = pts.str[0].astype(float)
geo["lat"] = pts.str[1].astype(float)

rows = []
for desc, lat, lon in zip(geo[G_DESC], geo["lat"], geo["lon"]):
    streets = sorted({n for n in (norm(s) for s in desc.split("/")) if n})
    # A 3-way description ("A / B / C") is reachable via any pair of its streets.
    for a, b in combinations(streets, 2):
        rows.append((key(a, b), lat, lon))
# The same pair can appear at several points (e.g. crescents meeting a road twice);
# averaging gives one representative location per key.
lookup = (pd.DataFrame(rows, columns=["key", "lat", "lon"])
          .groupby("key", as_index=False)[["lat", "lon"]].mean())
print(f"Intersection lookup: {len(lookup):,} street-pair keys from {len(geo):,} points")

# --- Match 311 requests ---
sr = pd.read_parquet(PROCESSED / "sr_access.parquet")
sr["key"] = [key(norm(a), norm(b)) for a, b in zip(sr[C_ST1], sr[C_ST2])]
has_pair = sr["key"].notna()
sr = sr.merge(lookup, on="key", how="left")
matched = sr["lat"].notna()

print(f"\n311 rows: {len(sr):,}")
print(f"  with both intersection streets: {has_pair.sum():,} ({has_pair.mean():.1%})")
print(f"  matched to coordinates:         {matched.sum():,}")
rate = matched.sum() / max(has_pair.sum(), 1)
print(f"Match rate (of rows with a street pair): {rate:.1%}")

unmatched = sr[has_pair & ~matched]
print("\nTop 20 unmatched street pairs (raw -> normalized key):")
top = unmatched.groupby([C_ST1, C_ST2, "key"]).size().sort_values(ascending=False).head(20)
print(top.to_string())

if rate < 0.5:
    print("\n!! Match rate is under 50%. Before continuing, look at the unmatched pairs above "
          "and extend norm() in common.py (e.g. more suffix/abbreviation rules).")

out = sr[matched].drop(columns="key")
out.to_parquet(PROCESSED / "sr_geocoded.parquet", index=False)
print(f"\nSaved {len(out):,} geocoded rows to {PROCESSED / 'sr_geocoded.parquet'}")
