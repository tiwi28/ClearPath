"""Refresh the app's 311 history: download the newest yearly 311 zips, then re-run 01-03 and 07.

Toronto publishes 311 data monthly, so run this monthly. The live model itself doesn't need
retraining for new history; re-run 04-06 and `05_train.py --live` when you want to refit it.

Usage: python 08_refresh_311.py [years]   (default: the current and previous year)
"""
import json
import subprocess
import sys
import urllib.request
from datetime import date

from common import ML, RAW

CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id=311-service-requests-customer-initiated"
years = [int(arg) for arg in sys.argv[1:]] or [date.today().year - 1, date.today().year]

resources = json.load(urllib.request.urlopen(CKAN, timeout=60))["result"]["resources"]
folder = RAW / "311"
folder.mkdir(parents=True, exist_ok=True)
for year in years:
    match = [r for r in resources if str(year) in r["name"] and r["url"].lower().endswith(".zip")]
    if not match:
        print(f"No 311 zip published for {year}")
        continue
    target = folder / f"311 Service Requests {year}.zip"
    print(f"Downloading {match[0]['name']} (updated {match[0].get('last_modified')}) -> {target.name}")
    urllib.request.urlretrieve(match[0]["url"], target)

for step in ("01_load_311.py", "02_filter_types.py", "03_geocode.py", "07_export.py"):
    print(f"\n=== {step}")
    subprocess.run([sys.executable, str(ML / step)], cwd=ML, check=True)
