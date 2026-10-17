"""Build the cell x day panel with leakage-free features and a 3-day-ahead target."""
import h3
import numpy as np
import pandas as pd

from common import PROCESSED, RAW

RES = 8
MIN_REQUESTS = 3

# --- Requests -> H3 cell counts per day ---
sr = pd.read_parquet(PROCESSED / "sr_geocoded.parquet", columns=["day", "lat", "lon"])
sr["cell"] = [h3.latlng_to_cell(lat, lon, RES) for lat, lon in zip(sr["lat"], sr["lon"])]

totals = sr["cell"].value_counts()
cells = totals[totals >= MIN_REQUESTS].index  # drop cells too sparse to learn anything from
counts = sr[sr["cell"].isin(cells)].groupby(["cell", "day"]).size()
print(f"{sr['cell'].nunique():,} cells with any request, {len(cells):,} with >= {MIN_REQUESTS}")

# Complete panel: every cell on every day. Days with no request are real zeros
# ("nobody complained"), not missing data, so the model must see them.
days = pd.date_range(sr["day"].min(), sr["day"].max(), freq="D")
idx = pd.MultiIndex.from_product([cells, days], names=["cell", "day"])
panel = counts.reindex(idx, fill_value=0).rename("n").astype("int16").reset_index()
panel = panel.sort_values(["cell", "day"], ignore_index=True)

# --- History features (only days strictly before t) ---
g = panel.groupby("cell", sort=False)
cum = g["n"].cumsum()                  # requests up to and including day t
prior = (cum - panel["n"]).astype("int32")   # requests before day t
panel["prior"] = prior
for w in (3, 7, 28, 365):
    # past_w = requests in [t-w, t-1] = prior_t - prior_{t-w}; before the panel starts prior is 0.
    panel[f"past{w}"] = (prior - g["prior"].shift(w, fill_value=0)).astype("int16")
day_idx = g.cumcount()                 # number of panel days before t
panel["rate_hist"] = (prior / day_idx.replace(0, np.nan)).astype("float32")

# --- Target: requests on days t+1..t+3 ---
panel["cum"] = cum
panel["future3"] = g["cum"].shift(-3) - panel["cum"]
panel = panel.dropna(subset=["future3"])  # last 3 days have no full future window
panel["future3"] = panel["future3"].astype("int16")
panel["y"] = (panel["future3"] > 0).astype("int8")
panel = panel.drop(columns=["prior", "cum"])

# --- Weather (city-wide, same value for every cell on a day) ---
def col(df, prefix):
    """Find a column by prefix, skipping '... Flag' columns (robust to a mangled degree sign)."""
    return next(c for c in df.columns if c.startswith(prefix) and not c.endswith("Flag"))

wx = pd.concat(pd.read_csv(f, encoding="utf-8-sig")
               for f in sorted((RAW / "weather").glob("*.csv")))
wx = pd.DataFrame({
    "day": pd.to_datetime(wx[col(wx, "Date/Time")]),
    "snow": wx[col(wx, "Total Snow")].fillna(0),
    "snow_ground": wx[col(wx, "Snow on Grnd")],
    "tmin": wx[col(wx, "Min Temp")],
    "tmax": wx[col(wx, "Max Temp")],
    "precip": wx[col(wx, "Total Precip")].fillna(0),
}).set_index("day").sort_index()
wx = wx.reindex(pd.date_range(wx.index.min(), wx.index.max(), freq="D"))
wx[["snow", "precip"]] = wx[["snow", "precip"]].fillna(0)
# Freeze-thaw days crack pavement and refreeze meltwater into ice.
wx["ft"] = ((wx["tmin"] < 0) & (wx["tmax"] > 0)).astype("int8")
# Trailing windows include today, which is known on day t, so no leakage.
wx["snow3"] = wx["snow"].rolling(3, min_periods=1).sum()
wx["snow7"] = wx["snow"].rolling(7, min_periods=1).sum()
wx["ft3"] = wx["ft"].rolling(3, min_periods=1).sum()
wx = wx.astype("float32").rename_axis("day").reset_index()

panel = panel.merge(wx, on="day", how="left")
panel["dow"] = panel["day"].dt.dayofweek.astype("int8")
panel["month"] = panel["day"].dt.month.astype("int8")

# --- Sanity check: recompute one busy cell with a slow loop ---
c = totals.index[0]
s = panel[panel["cell"] == c].set_index("day")
full = counts.loc[c].reindex(days, fill_value=0)
for t in s.index[400:410]:
    assert s.at[t, "past7"] == full[t - pd.Timedelta(days=7):t - pd.Timedelta(days=1)].sum()
    assert s.at[t, "future3"] == full[t + pd.Timedelta(days=1):t + pd.Timedelta(days=3)].sum()
print("Leakage check passed (past7 / future3 match a manual loop)")

print(f"\nPanel shape: {panel.shape}")
print(f"Days: {panel['day'].min().date()} to {panel['day'].max().date()}")
print(f"Positive rate of y: {panel['y'].mean():.2%}")
print(panel.sample(5, random_state=0).to_string())

panel.to_parquet(PROCESSED / "panel.parquet", index=False)
print(f"\nSaved {PROCESSED / 'panel.parquet'}")
