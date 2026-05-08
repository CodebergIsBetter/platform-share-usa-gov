"""
Calculate daily Linux % of all included (desktop) OS visits across DAP data.

Outputs a Desmos-ready list: Y=[2.3, 2.1, ...]
Also saves to linux_daily_pct.txt.

On first run (or when new OS names appear), you'll be prompted to
classify unknown OSes as included or excluded. Your choices are saved
to os_filter.json so you won't be asked again.
"""

import json
import glob
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
FILTER_FILE = SCRIPT_DIR / "os_filter.json"
OUTPUT_FILE = SCRIPT_DIR / "linux_daily_pct.txt"

# OS names that count as "Linux" in the numerator
LINUX_NAMES = {"Linux", "Linux x86_64", "Linux armv8l"}


def load_filter() -> dict:
    """Load the OS filter from os_filter.json, or return empty lists if it doesn't exist."""
    if FILTER_FILE.exists():
        with open(FILTER_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "include": [],
        "exclude": [],
    }


def save_filter(filt: dict):
    with open(FILTER_FILE, "w", encoding="utf-8") as f:
        json.dump(filt, f, indent=2)


def prompt_unknown(os_names: set, filt: dict, records: list) -> dict:
    """Ask the user about any OS not yet classified."""
    known = set(filt["include"]) | set(filt["exclude"])
    unknown = sorted(os_names - known)

    if not unknown:
        return filt

    # Count total visits per unknown OS for context
    from collections import Counter
    os_visits = Counter()
    for r in records:
        if r["os"] in unknown:
            os_visits[r["os"]] += int(r.get("visits", 0))

    interactive = sys.stdin.isatty()

    if not interactive:
        # CI / non-interactive: auto-exclude unknown OSes
        print(f"\n  WARNING: {len(unknown)} new OS name(s) auto-excluded (non-interactive):")
        for name in sorted(unknown, key=lambda n: os_visits[n], reverse=True):
            print(f"    - '{name}' ({os_visits[name]:,} visits)")
            filt["exclude"].append(name)
        filt["exclude"] = sorted(set(filt["exclude"]))
        save_filter(filt)
        print("  Update os_filter.json manually if any should be included.\n")
        return filt

    print(f"\n{'='*60}")
    print(f"  {len(unknown)} unclassified OS name(s) found.")
    print(f"  Type 'i' to INCLUDE (desktop) or 'e' to EXCLUDE.")
    print(f"{'='*60}\n")

    for name in sorted(unknown, key=lambda n: os_visits[n], reverse=True):
        while True:
            choice = input(f"  '{name}' ({os_visits[name]:,} visits)  [i]nclude / [e]xclude: ").strip().lower()
            if choice in ("i", "e"):
                break
            print("    → please enter 'i' or 'e'")

        if choice == "i":
            filt["include"].append(name)
        else:
            filt["exclude"].append(name)

    filt["include"] = sorted(set(filt["include"]))
    filt["exclude"] = sorted(set(filt["exclude"]))
    save_filter(filt)
    print("\n  Filter saved to os_filter.json\n")
    return filt


def collect_all_records() -> list:
    """Load records from both API versions, deduplicating the overlap.

    v1.1 covers 2018-01-01 to 2024-06-23 (Universal Analytics).
    v2   covers 2023-08-01 to present    (GA4).
    Overlap is 2023-08-01 to 2024-06-23.

    Strategy: use v1.1 for dates up to its last date, then v2 for
    dates after that. This avoids double-counting.
    """
    # Find the last date in v1.1
    v1_files = sorted(glob.glob(str(DATA_DIR / "v1.1/*.json")))
    v1_max_date = ""
    v1_records = []
    for filepath in v1_files:
        with open(filepath, encoding="utf-8") as f:
            for r in json.load(f):
                v1_records.append(r)
                d = r["date"][:10]
                if d > v1_max_date:
                    v1_max_date = d

    # Load v2, but only dates AFTER v1.1's last date
    v2_records = []
    for filepath in sorted(glob.glob(str(DATA_DIR / "v2/*.json"))):
        with open(filepath, encoding="utf-8") as f:
            for r in json.load(f):
                if r["date"][:10] > v1_max_date:
                    v2_records.append(r)

    print(f"  v1.1: {len(v1_records)} records (up to {v1_max_date})")
    print(f"  v2:   {len(v2_records)} records (from dates after {v1_max_date})")

    return v1_records + v2_records


def discover_os_names(records: list) -> set:
    return {r["os"] for r in records}


def compute_daily_pct(records: list, include_set: set) -> list:
    """Return list of (date_str, linux_pct) sorted by date."""
    # Aggregate visits per day
    daily_linux = defaultdict(int)
    daily_total = defaultdict(int)

    for r in records:
        os_name = r["os"]
        if os_name not in include_set:
            continue
        visits = int(r.get("visits", 0))
        day = r["date"][:10]  # "YYYY-MM-DD"
        daily_total[day] += visits
        if os_name in LINUX_NAMES:
            daily_linux[day] += visits

    results = []
    for day in sorted(daily_total):
        total = daily_total[day]
        if total > 0:
            pct = round(daily_linux[day] / total * 100, 4)
        else:
            pct = 0.0
        results.append((day, pct))

    return results


def main():
    # 1. Load all data
    print("Loading data...")
    records = collect_all_records()
    print(f"  {len(records)} records loaded.\n")

    # 2. Discover OS names and handle unknowns
    all_os = discover_os_names(records)
    filt = load_filter()
    filt = prompt_unknown(all_os, filt, records)
    save_filter(filt)

    include_set = set(filt["include"])

    print(f"Included OSes ({len(include_set)}): {', '.join(sorted(include_set))}")
    print(f"Linux names:    {', '.join(sorted(LINUX_NAMES & include_set))}")
    print()

    # 3. Compute daily Linux %
    print("Computing daily Linux %...")
    daily = compute_daily_pct(records, include_set)
    print(f"  {len(daily)} days of data ({daily[0][0]} → {daily[-1][0]})\n")

    # 4. Build Desmos output
    pcts = [d[1] for d in daily]
    desmos_str = "Y=[" + ",".join(str(p) for p in pcts) + "]"

    # Print to console
    print(desmos_str[:200] + ("..." if len(desmos_str) > 200 else ""))
    print(f"\n  Full list length: {len(pcts)} values")

    # 5. Save to file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(desmos_str + "\n")
        f.write("\n# Date → Linux %\n")
        for day, pct in daily:
            f.write(f"# {day}  {pct}%\n")

    print(f"  Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
