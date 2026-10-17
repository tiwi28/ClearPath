"""Train the LightGBM risk model with a time-based split.

Usage: python 05_train.py [--live]
  --live trains the model the app runs today: history features stop LAG days before t,
  because Toronto publishes 311 data monthly. Saves risk_model_live.txt.
"""
import sys

import lightgbm as lgb
import pandas as pd

from common import ML, PROCESSED

WEATHER = ["snow", "snow_ground", "tmin", "tmax", "precip", "ft", "snow3", "snow7", "ft3"]
FEATURES = ["past3", "past7", "past28", "past365", "rate_hist", *WEATHER, "dow", "month"]
LIVE_FEATURES = ["lag_past28", "lag_past91", "lag_past365", "lag_rate_hist", "season_last_year",
                 *WEATHER, "dow", "month"]
live = "--live" in sys.argv
features = LIVE_FEATURES if live else FEATURES
suffix = "_live" if live else ""
TEST_START = pd.Timestamp("2025-11-01")
# Training targets look 3 days ahead, so stop training 3 days before the test
# period; otherwise the last training labels would peek into test days.
TRAIN_END = pd.Timestamp("2025-10-29")

panel = pd.read_parquet(PROCESSED / "panel.parquet")
train = panel[panel["day"] < TRAIN_END]
test = panel[panel["day"] >= TEST_START]
print(f"Train: {len(train):,} rows ({train['day'].min().date()} to {train['day'].max().date()}), "
      f"positive rate {train['y'].mean():.2%}")
print(f"Test:  {len(test):,} rows ({test['day'].min().date()} to {test['day'].max().date()}), "
      f"positive rate {test['y'].mean():.2%}")

model = lgb.LGBMClassifier(
    n_estimators=400, learning_rate=0.05, num_leaves=63,
    subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
    verbose=-1,
)
model.fit(train[features], train["y"])
model.booster_.save_model(str(ML / f"risk_model{suffix}.txt"))
print(f"\nSaved model to {ML / f'risk_model{suffix}.txt'}")

preds = test[["cell", "day", "y", "future3", "rate_hist", "lag_rate_hist", "past7", "snow3"]].copy()
preds["risk"] = model.predict_proba(test[features])[:, 1]
preds.to_parquet(PROCESSED / f"test_preds{suffix}.parquet", index=False)
print(f"Saved {len(preds):,} test predictions to {PROCESSED / f'test_preds{suffix}.parquet'}")
print(preds["risk"].describe().to_string())
