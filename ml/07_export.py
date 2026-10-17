"""Export risk scores for the app: a GeoJSON for the demo storm day and a CSV for the test period."""
import json

import h3
import pandas as pd

from common import OUT, PROCESSED

p = pd.read_parquet(PROCESSED / "test_preds.parquet")

# Demo date: the test day with the most snow over the trailing 3 days.
storm = p.loc[p["snow3"].idxmax(), "day"]
day = p[p["day"] == storm]
print(f"Demo storm date: {storm.date()} (snow3 = {day['snow3'].iloc[0]:.1f} cm, "
      f"{len(day)} cells, {int((day['future3'] > 0).sum())} with a complaint in the next 3 days)")

features = []
for cell, risk, actual in zip(day["cell"], day["risk"], day["future3"]):
    # h3 returns (lat, lng); GeoJSON wants [lng, lat] and a closed ring.
    ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(cell)]
    ring.append(ring[0])
    features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"cell": cell, "risk": round(float(risk), 3), "actual": int(actual)},
    })

geojson_path = OUT / "risk_storm.geojson"
geojson_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
print(f"Saved {len(features)} polygons to {geojson_path}")

csv_path = OUT / "risk_scores.csv"
out = p[["cell", "day", "risk"]].copy()
out["day"] = out["day"].dt.strftime("%Y-%m-%d")
out["risk"] = out["risk"].round(3)
out.to_csv(csv_path, index=False)
print(f"Saved {len(out):,} rows to {csv_path}")
print("\nRiskiest cells on the storm day:")
print(day.nlargest(5, "risk")[["cell", "risk", "future3"]].to_string(index=False))
