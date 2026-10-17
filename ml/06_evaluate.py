"""Evaluate the model against simple baselines and plot feature importance."""
import lightgbm as lgb
import matplotlib

matplotlib.use("Agg")  # write the PNG without needing a display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from common import ML, PROCESSED

p = pd.read_parquet(PROCESSED / "test_preds.parquet")
p["rate_hist"] = p["rate_hist"].fillna(0)

scores = {"model": "risk", "historical rate": "rate_hist", "last 7 days": "past7"}
print(f"Test set: {len(p):,} cell-days, positive rate {p['y'].mean():.2%}\n")
print(f"{'score':<16} {'ROC-AUC':>8} {'PR-AUC':>8}")
for name, c in scores.items():
    print(f"{name:<16} {roc_auc_score(p['y'], p[c]):>8.3f} {average_precision_score(p['y'], p[c]):>8.3f}")


def top10_capture(df, score):
    """Share of all positive cell-days that fall in each day's top 10% highest-scored cells."""
    # Rank within each day; method="first" breaks ties so exactly 10% are picked.
    rank = df.groupby("day")[score].rank(method="first", ascending=False)
    k = np.ceil(0.10 * df.groupby("day")[score].transform("size"))
    return df.loc[rank <= k, "y"].sum() / df["y"].sum()


cap_model = top10_capture(p, "risk")
cap_base = top10_capture(p, "rate_hist")
print(f"\nTop 10% capture (share of positives found by flagging 10% of cells each day):")
print(f"  model:           {cap_model:.1%}")
print(f"  historical rate: {cap_base:.1%}")

# Season breakdown: the test set is one winter, so check the model isn't only winning on snow days.
p["season"] = np.where(p["day"].dt.month.isin([11, 12, 1, 2, 3]), "winter (Nov-Mar)", "rest (Apr-Oct)")
print("\nBy season:")
print(f"{'season':<17} {'rows':>8} {'pos':>6} | {'ROC model':>9} {'ROC rate':>8} {'ROC past7':>9} "
      f"| {'PR model':>8} {'PR rate':>7} {'PR past7':>8} | {'cap model':>9} {'cap rate':>8}")
for season, s in p.groupby("season"):
    roc = [roc_auc_score(s["y"], s[c]) for c in scores.values()]
    pr = [average_precision_score(s["y"], s[c]) for c in scores.values()]
    print(f"{season:<17} {len(s):>8,} {s['y'].mean():>6.1%} | {roc[0]:>9.3f} {roc[1]:>8.3f} {roc[2]:>9.3f} "
          f"| {pr[0]:>8.3f} {pr[1]:>7.3f} {pr[2]:>8.3f} "
          f"| {top10_capture(s, 'risk'):>9.1%} {top10_capture(s, 'rate_hist'):>8.1%}")

# Feature importance by gain (how much each feature improved the splits).
booster = lgb.Booster(model_file=str(ML / "risk_model.txt"))
imp = pd.Series(booster.feature_importance("gain"), index=booster.feature_name()).sort_values()
fig, ax = plt.subplots(figsize=(7, 5))
ax.barh(imp.index, imp.values / imp.sum())
ax.set_xlabel("Share of total gain")
ax.set_title("Clearpath risk model: feature importance")
fig.tight_layout()
fig.savefig(ML / "feature_importance.png", dpi=150)
print(f"\nSaved {ML / 'feature_importance.png'}")
print("Top features:", ", ".join(imp.index[::-1][:5]))

# Weather is city-wide, so it helps decide WHEN risk is high (pooled AUC) but not
# WHICH cells are riskiest on a given day (daily capture). Say both honestly.
auc_m, auc_b = roc_auc_score(p["y"], p["risk"]), roc_auc_score(p["y"], p["rate_hist"])
print("\nSlide summary:")
print(f"On held-out data from Nov 2025 to Sep 2026, our model predicts where accessibility complaints will appear "
      f"in the next 3 days with a ROC-AUC of {auc_m:.2f}, versus {auc_b:.2f} for historical complaint "
      f"rates, mainly because snowfall and freeze-thaw weather tell it when risk spikes across the city. "
      f"On any single day, flagging the riskiest 10% of areas catches {cap_model:.0%} of upcoming "
      f"complaints (a random 10% would catch about 10%).")

# The live model (05_train.py --live) is what the app runs today: it only sees reports
# older than LAG days because Toronto publishes 311 data monthly.
live_path = PROCESSED / "test_preds_live.parquet"
if live_path.exists():
    q = pd.read_parquet(live_path)
    q["lag_rate_hist"] = q["lag_rate_hist"].fillna(0)
    print("\nLive model (history older than LAG days only):")
    print(f"{'score':<20} {'ROC-AUC':>8} {'PR-AUC':>8} {'top10%':>8}")
    for name, frame, c in (("original model", p, "risk"), ("live model", q, "risk"),
                           ("lagged hist. rate", q, "lag_rate_hist")):
        print(f"{name:<20} {roc_auc_score(frame['y'], frame[c]):>8.3f} "
              f"{average_precision_score(frame['y'], frame[c]):>8.3f} {top10_capture(frame, c):>8.1%}")
