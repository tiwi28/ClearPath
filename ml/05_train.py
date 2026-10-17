"""Train the LightGBM risk model with a time-based split."""
import lightgbm as lgb
import pandas as pd

from common import ML, PROCESSED

FEATURES = [
    "past3", "past7", "past28", "past365", "rate_hist",
    "snow", "snow_ground", "tmin", "tmax", "precip", "ft", "snow3", "snow7", "ft3",
    "dow", "month",
]
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
model.fit(train[FEATURES], train["y"])
model.booster_.save_model(str(ML / "risk_model.txt"))
print(f"\nSaved model to {ML / 'risk_model.txt'}")

preds = test[["cell", "day", "y", "future3", "rate_hist", "past7", "snow3"]].copy()
preds["risk"] = model.predict_proba(test[FEATURES])[:, 1]
preds.to_parquet(PROCESSED / "test_preds.parquet", index=False)
print(f"Saved {len(preds):,} test predictions to {PROCESSED / 'test_preds.parquet'}")
print(preds["risk"].describe().to_string())
