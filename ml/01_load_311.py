"""Load all yearly 311 zips into one parquet file."""
import pandas as pd

from common import PROCESSED, RAW

frames = []
for z in sorted((RAW / "311").glob("*.zip")):
    # dtype=str: keep everything raw here; parsing happens in later steps.
    df = pd.read_csv(z, dtype=str, on_bad_lines="skip", encoding_errors="replace")
    # Some files start with a UTF-8 BOM, which str.strip() does not remove.
    df.columns = df.columns.str.replace("﻿", "").str.strip().str.lower()
    print(f"{z.name}: {len(df):,} rows")
    frames.append(df)

sr = pd.concat(frames, ignore_index=True)
print(f"\nTotal: {len(sr):,} rows")
print("Columns:", list(sr.columns))
print(sr.sample(5, random_state=0).to_string())

sr.to_parquet(PROCESSED / "sr_all.parquet", index=False)
print(f"\nSaved {PROCESSED / 'sr_all.parquet'}")
