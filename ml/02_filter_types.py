"""Filter 311 requests to accessibility-related types.

First run (no accessibility_types.csv): write candidate_types.csv and stop,
so a human picks the keepers. Second run: filter and parse dates.
"""
import sys

import pandas as pd

from common import C_DATE, C_TYPE, ML, PROCESSED

sr = pd.read_parquet(PROCESSED / "sr_all.parquet")
keep_file = ML / "accessibility_types.csv"

if not keep_file.exists():
    # Word boundaries so "ice" doesn't match "Service", "ramp" doesn't match "rampant", etc.
    kw = r"\b(?:sidewalks?|curbs?|snow|ice|icy|ramps?|obstruct\w*|walkways?|boulevards?)\b"
    m = sr[C_TYPE].str.contains(kw, case=False, na=False, regex=True)
    cand = (sr.loc[m, C_TYPE].value_counts()
            .rename_axis("type").reset_index(name="count"))
    cand.to_csv(ML / "candidate_types.csv", index=False)
    pd.set_option("display.width", 200)
    print(cand.to_string(index=False))
    print(f"\n{len(cand)} candidate types written to {ML / 'candidate_types.csv'}")
    print("Copy the keepers into ml/accessibility_types.csv (single column 'type'), then rerun.")
    sys.exit(0)

types = pd.read_csv(keep_file)["type"].str.strip()
acc = sr[sr[C_TYPE].str.strip().isin(set(types))].copy()

# Dates look like "2025-01-01 00:01:05.0000000"; the day is all we need.
acc["day"] = pd.to_datetime(acc[C_DATE].str[:10], format="%Y-%m-%d", errors="coerce")
n0 = len(acc)
acc = acc.dropna(subset=["day"])
print(f"Kept {len(acc):,} rows across {acc[C_TYPE].nunique()} types "
      f"(dropped {n0 - len(acc):,} without a valid date)")
print(acc[C_TYPE].value_counts().to_string())
print("Day range:", acc["day"].min().date(), "to", acc["day"].max().date())

acc.to_parquet(PROCESSED / "sr_access.parquet", index=False)
print(f"\nSaved {PROCESSED / 'sr_access.parquet'}")
