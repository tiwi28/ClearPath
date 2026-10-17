# Clearpath ML: accessibility barrier risk

Predicts, for each H3 resolution-8 cell in Toronto (about 0.7 km²), the probability of an
accessibility-related 311 complaint (uncleared or icy sidewalk, damaged sidewalk or curb,
broken ramp, ...) in the next 3 days. The app uses these scores to route around likely
barriers and warn users before they reach them.

## Setup

```powershell
cd ml
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install h3 pandas lightgbm scikit-learn matplotlib pyarrow
```

Raw data goes in the repo-root `data/raw/` (gitignored, nothing is downloaded by the scripts):

| Folder | Contents |
|---|---|
| `data/raw/311/` | Toronto "311 Service Requests - Customer Initiated" yearly zips |
| `data/raw/weather/` | Environment Canada daily CSVs, Toronto Pearson (climate ID 6158731) |
| `data/raw/geo/` | `Centreline Intersection - 4326.csv` from Toronto Open Data |

## Run order

Run from inside `ml/`. Each step reads the previous step's output, so any step can be rerun alone.

| Step | What it does | Output |
|---|---|---|
| `01_load_311.py` | Concatenate all 311 zips, clean column names | `data/processed/sr_all.parquet` |
| `02_filter_types.py` | 1st run: list keyword-matched request types and stop. 2nd run: keep types in `accessibility_types.csv` | `ml/candidate_types.csv`, then `data/processed/sr_access.parquet` |
| `03_geocode.py` | Match each request's two intersection streets to the centreline file | `data/processed/sr_geocoded.parquet` |
| `04_build_panel.py` | Cell x day panel, history + weather + calendar features, 3-day-ahead target | `data/processed/panel.parquet` |
| `05_train.py` | Train LightGBM; test = from 2025-11-01, train = before 2025-10-29 | `ml/risk_model.txt`, `data/processed/test_preds.parquet` |
| `06_evaluate.py` | ROC/PR-AUC vs baselines, daily top-10% capture, slide summary | `ml/feature_importance.png` |
| `07_export.py` | Demo storm day map + full test-period scores | `data/risk_storm.geojson`, `data/risk_scores.csv` |

`common.py` holds paths, column names, and the street-name normalization (`norm`, `key`).
`accessibility_types.csv` is the hand-picked list of 311 types that count as barriers.

## Outputs for the app

- **`data/risk_storm.geojson`**: one hexagon polygon per cell for the demo storm date
  (the test day with the most 3-day snowfall). Properties: `cell`, `risk` (0 to 1), `actual`
  (complaints that really came in over the next 3 days). Drop it straight onto the map.
- **`data/risk_scores.csv`**: `cell, day, risk` for every cell and day in the test period.
  The backend can join a route's H3 cells to these scores.
- **`ml/risk_model.txt`**: the LightGBM model, loadable with `lightgbm.Booster(model_file=...)`.

## Design notes

- **No leakage.** History features count only days before `t`, and the target counts days `t+1..t+3`.
  The train/test split leaves a 3-day gap so training labels don't overlap test days.
  `04_build_panel.py` asserts a few rows against a slow manual loop.
- **Zero-filled panel.** A day with no complaint is a real "no", so every cell gets a row for every day.
- **Weather is city-wide** (one airport station). It tells the model *when* risk spikes, but not
  *which* cells are riskiest on a given day. That comes from each cell's complaint history.
- **Coverage.** Only requests with two intersection streets can be geocoded (about 30% of the chosen
  types). Snow and ice reports include street names far more often than damaged-sidewalk reports, so
  the model leans toward winter barriers. See `docs/data-limits.md`.
