"""Export the live risk model and its inputs for the backend (backend/app/data/).

The backend predicts risk for today and the next two days from these files plus a
live weather forecast, so nothing here is tied to a past "demo day".

Writes:
  risk_cells.geojson   one H3 polygon per modelled cell (no scores)
  cell_counts.csv      cell, day, n: daily geocoded accessibility reports, nonzero only
  cell_totals.csv      cell, prior: reports before the first day in cell_counts.csv
  risk_model_live.txt  LightGBM model from 05_train.py --live
  model_meta.json      feature order, LAG, reports_through, test metrics
"""
import json
import shutil

import h3
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from common import APP_DATA, LAG, ML, PROCESSED

RES = 8
MIN_REQUESTS = 3
HISTORY_DAYS = 800  # covers lag_past365 and season_last_year for the next few months

APP_DATA.mkdir(parents=True, exist_ok=True)
sr = pd.read_parquet(PROCESSED / "sr_geocoded.parquet", columns=["day", "lat", "lon"])
sr["cell"] = [h3.latlng_to_cell(lat, lon, RES) for lat, lon in zip(sr["lat"], sr["lon"])]
totals = sr["cell"].value_counts()
cells = sorted(totals[totals >= MIN_REQUESTS].index)  # same cells as 04_build_panel.py
reports_through = sr["day"].max()

features = []
for cell in cells:
    # h3 returns (lat, lng); GeoJSON wants [lng, lat] and a closed ring.
    ring = [[round(lng, 6), round(lat, 6)] for lat, lng in h3.cell_to_boundary(cell)]
    ring.append(ring[0])
    features.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                     "properties": {"cell": cell}})
(APP_DATA / "risk_cells.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}))

recent = sr[sr["cell"].isin(cells) & (sr["day"] > reports_through - pd.Timedelta(days=HISTORY_DAYS))]
counts = recent.groupby(["cell", "day"]).size().rename("n").reset_index()
counts["day"] = counts["day"].dt.strftime("%Y-%m-%d")
counts.to_csv(APP_DATA / "cell_counts.csv", index=False)
# lag_rate_hist needs every report since the panel started, not just the recent window.
first_day = pd.Timestamp(counts["day"].min())
older = sr[sr["cell"].isin(cells) & (sr["day"] < first_day)]["cell"].value_counts()
older.reindex(cells, fill_value=0).rename_axis("cell").rename("prior").reset_index().to_csv(
    APP_DATA / "cell_totals.csv", index=False)

shutil.copy(ML / "risk_model_live.txt", APP_DATA / "risk_model_live.txt")
q = pd.read_parquet(PROCESSED / "test_preds_live.parquet")
rank = q.groupby("day")["risk"].rank(method="first", ascending=False)
top10 = q.loc[rank <= np.ceil(0.10 * q.groupby("day")["risk"].transform("size")), "y"].sum() / q["y"].sum()
meta = {
    "lag_days": LAG,
    "panel_start": sr["day"].min().strftime("%Y-%m-%d"),  # 04_build_panel.py counts days from here
    "first_history_day": counts["day"].min(),
    "reports_through": reports_through.strftime("%Y-%m-%d"),
    "test_period": [q["day"].min().strftime("%Y-%m-%d"), q["day"].max().strftime("%Y-%m-%d")],
    "roc_auc": round(float(roc_auc_score(q["y"], q["risk"])), 3),
    "pr_auc": round(float(average_precision_score(q["y"], q["risk"])), 3),
    "top10_capture": round(float(top10), 3),
}
(APP_DATA / "model_meta.json").write_text(json.dumps(meta, indent=2) + "\n")

print(f"{len(cells)} cells, {len(counts):,} cell-days with reports, reports through {meta['reports_through']}")
print(json.dumps(meta, indent=2))
print(f"Saved to {APP_DATA}")
