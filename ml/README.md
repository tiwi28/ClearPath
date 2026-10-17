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
| `05_train.py [--live]` | Train LightGBM; test = from 2025-11-01, train = before 2025-10-29. `--live` trains on history older than `LAG` days only | `ml/risk_model.txt` or `ml/risk_model_live.txt`, `data/processed/test_preds[_live].parquet` |
| `06_evaluate.py` | ROC/PR-AUC vs baselines, daily top-10% capture, slide summary, live vs original model | `ml/feature_importance.png` |
| `07_export.py` | Export the live model and its inputs for the backend | `backend/app/data/` (see below) |
| `08_refresh_311.py` | Download the newest 311 zips from Toronto Open Data, re-run 01-03 and 07. Run monthly | refreshed `backend/app/data/` |

`common.py` holds paths, column names, `LAG`, and the street-name normalization (`norm`, `key`).
`accessibility_types.csv` is the hand-picked list of 311 types that count as barriers.

## Live predictions ("use the past to predict now")

The app predicts risk for today and the next two days; it never replays a past day.

- Toronto publishes 311 data **monthly** (around the 8th, through the end of the previous month), so on
  any day the newest report can be ~40 days old. The live model's history features
  (`lag_past28/91/365`, `lag_rate_hist`, `season_last_year`) only use reports older than `LAG = 40` days,
  so it never depends on data that wouldn't exist yet.
- Weather comes live from the Open-Meteo forecast for Toronto Pearson, built into the same features as
  training (`snow`, `snow_ground`, `tmin`, `tmax`, `precip`, freeze-thaw, 3/7-day sums).
- `backend/app/forecast.py` rebuilds the features exactly like `04_build_panel.py` (checked against the
  panel on test days) and runs `risk_model_live.txt`.

| Model (test: Nov 2025 to Sep 2026) | ROC-AUC | PR-AUC | Top-10% capture |
|---|---|---|---|
| Original (needs reports up to yesterday) | 0.863 | 0.422 | 27.8% |
| **Live (reports older than 40 days + live weather)** | **0.856** | **0.392** | **26.0%** |
| Historical complaint rate, lagged | 0.694 | 0.117 | 27.5% |

Losing the last 40 days of reports costs very little; weather does most of the work of saying *when*
risk spikes. Ranking *which* cells are riskiest on a given day is still mostly history, which is why the
daily top-10% capture is close to the historical-rate baseline.

## Outputs for the app (`backend/app/data/`, written by `07_export.py`)

- **`risk_cells.geojson`**: one H3 resolution-8 hexagon (about 0.7 km²) per modelled cell (753 cells with
  at least 3 past reports). Areas without a hexagon have too few reports to predict.
- **`cell_counts.csv`**, **`cell_totals.csv`**: daily geocoded report counts per cell for the last ~800
  days, plus each cell's earlier total (needed for `lag_rate_hist`).
- **`risk_model_live.txt`**: the live LightGBM model.
- **`model_meta.json`**: `LAG`, panel start, `reports_through`, and the live model's test metrics.

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
