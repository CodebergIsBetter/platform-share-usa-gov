"""
Fetch OS usage data from the DAP (Digital Analytics Program) API.

Covers two API versions for maximum time range:
  - v1.1: Jan 2018 - Jun 2024  (Universal Analytics)
  - v2:   Aug 2023 - present    (GA4)

Data is saved as one JSON file per month per API version.
Already-downloaded months are skipped automatically.
"""

import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

API_KEY = os.environ.get("DAP_API_KEY", "")
if not API_KEY:
    sys.exit("ERROR: Set the DAP_API_KEY environment variable.")
BASE_URL = "https://api.gsa.gov/analytics/dap"
HEADERS = {"x-api-key": API_KEY}
PAGE_LIMIT = 10000  # max allowed by API

# Each API version and its valid date range
API_VERSIONS = [
    {
        "version": "v1.1",
        "start": date(2018, 1, 1),
        "end": date(2024, 6, 24),
    },
    {
        "version": "v2",
        "start": date(2023, 8, 1),
        "end": None,  # None means "today"
    },
]

DATA_DIR = Path(__file__).parent


def months_in_range(start: date, end: date):
    """Yield (year, month) tuples for every month from start to end (inclusive)."""
    current = start.replace(day=1)
    while current <= end:
        yield current.year, current.month
        # advance to first of next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def last_day_of_month(year: int, month: int) -> date:
    """Return the last day of the given month."""
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def fetch_month(version: str, year: int, month: int) -> list:
    """Fetch all pages of OS data for a single month from the API."""
    after = date(year, month, 1).isoformat()
    before = last_day_of_month(year, month).isoformat()

    url = f"{BASE_URL}/{version}/reports/os/data"
    all_records = []
    page = 1

    while True:
        params = {
            "after": after,
            "before": before,
            "limit": PAGE_LIMIT,
            "page": page,
        }
        resp = requests.get(url, headers=HEADERS, params=params, timeout=60)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 10))
            print(f"    Rate limited. Waiting {retry_after}s...")
            time.sleep(retry_after)
            continue

        resp.raise_for_status()
        data = resp.json()

        if not data:
            break

        all_records.extend(data)

        if len(data) < PAGE_LIMIT:
            break

        page += 1
        time.sleep(0.5)  # polite pacing between pages

    return all_records


def main():
    today = date.today()

    for api in API_VERSIONS:
        version = api["version"]
        start = api["start"]
        end = min(api["end"] or today, today)

        version_dir = DATA_DIR / version
        version_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"API {version}  |  {start} → {end}")
        print(f"{'='*60}")

        for year, month in months_in_range(start, end):
            filename = f"{year}-{month:02d}.json"
            filepath = version_dir / filename

            # Never download the current (incomplete) month
            if year == today.year and month == today.month:
                print(f"  [SKIP]  {version}/{filename} (current month, incomplete)")
                continue

            if filepath.exists():
                print(f"  [SKIP]  {version}/{filename} already exists")
                continue

            month_end = last_day_of_month(year, month)
            if month_end > end:
                # For partial final months, still fetch what's available
                pass

            print(f"  [FETCH] {version}/{filename} ...", end=" ", flush=True)
            try:
                records = fetch_month(version, year, month)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2)
                print(f"{len(records)} records")
            except requests.HTTPError as e:
                print(f"HTTP ERROR {e.response.status_code}: {e}")
            except Exception as e:
                print(f"ERROR: {e}")

            time.sleep(1)  # pacing between months

    print("\nDone.")


if __name__ == "__main__":
    main()
