"""
Generate README.md with desktop and mobile platform share graphs.

Uses DAP (Digital Analytics Program) OS visit data from ../data and
classification rules from os_filter.json.

Outputs:
  - assets/desktop-platforms.png
  - assets/mobile-platforms.png
  - ../README.md
"""

from __future__ import annotations

import glob
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).parent
REPO_DIR = SCRIPT_DIR.parent
DATA_DIR = REPO_DIR / "data"
FILTER_FILE = SCRIPT_DIR / "os_filter.json"
ASSETS_DIR = REPO_DIR / "assets"
README_FILE = REPO_DIR / "README.md"


def platform_order(filt: dict, category: str) -> list[str]:
    return list(filt[category].keys())


def platform_colors(filt: dict, category: str) -> dict[str, str]:
    return {platform: config["color"] for platform, config in filt[category].items()}


def load_filter() -> dict:
    with open(FILTER_FILE, encoding="utf-8") as f:
        return json.load(f)


def build_os_to_platform(filt: dict) -> dict[str, tuple[str, str]]:
    """Map raw DAP OS names to (category, platform) e.g. ('desktop', 'LINUX')."""
    mapping: dict[str, tuple[str, str]] = {}
    for platform, config in filt["desktop"].items():
        for name in config["names"]:
            mapping[name] = ("desktop", platform)
    for platform, config in filt["mobile"].items():
        for name in config["names"]:
            mapping[name] = ("mobile", platform)
    return mapping


def collect_all_records() -> list:
    """Load records from both API versions, deduplicating the overlap."""
    v1_files = sorted(glob.glob(str(DATA_DIR / "v1.1/*.json")))
    v1_max_date = ""
    v1_records = []
    for filepath in v1_files:
        with open(filepath, encoding="utf-8") as f:
            for record in json.load(f):
                v1_records.append(record)
                day = record["date"][:10]
                if day > v1_max_date:
                    v1_max_date = day

    v2_records = []
    for filepath in sorted(glob.glob(str(DATA_DIR / "v2/*.json"))):
        with open(filepath, encoding="utf-8") as f:
            for record in json.load(f):
                if record["date"][:10] > v1_max_date:
                    v2_records.append(record)

    return v1_records + v2_records


def warn_unknown_os(records: list, os_to_platform: dict, exclude_set: set) -> None:
    """Report unclassified OS names in non-interactive mode."""
    known = set(os_to_platform) | exclude_set
    unknown = sorted({r["os"] for r in records} - known)
    if not unknown:
        return

    visits = Counter()
    for record in records:
        if record["os"] in unknown:
            visits[record["os"]] += int(record.get("visits", 0))

    print(f"WARNING: {len(unknown)} unclassified OS name(s) (auto-excluded):")
    for name in sorted(unknown, key=lambda n: visits[n], reverse=True):
        print(f"  - '{name}' ({visits[name]:,} visits)")
    if sys.stdin.isatty():
        print("  Update analysis/os_filter.json if any should be tracked.\n")


def aggregate_monthly(
    records: list,
    os_to_platform: dict,
    exclude_set: set,
    desktop_order: list[str],
    mobile_order: list[str],
) -> tuple[list[datetime], dict[str, list[float]], dict[str, list[float]]]:
    """Return monthly dates and platform share series for desktop and mobile."""
    monthly_desktop = defaultdict(lambda: defaultdict(int))
    monthly_mobile = defaultdict(lambda: defaultdict(int))

    for record in records:
        os_name = record["os"]
        if os_name in exclude_set:
            continue

        category_platform = os_to_platform.get(os_name)
        if not category_platform:
            continue

        category, platform = category_platform
        visits = int(record.get("visits", 0))
        month_key = record["date"][:7]  # YYYY-MM

        if category == "desktop":
            monthly_desktop[month_key][platform] += visits
        else:
            monthly_mobile[month_key][platform] += visits

    month_keys = sorted(set(monthly_desktop) | set(monthly_mobile))
    dates = [datetime.strptime(m, "%Y-%m") for m in month_keys]

    desktop_series: dict[str, list[float]] = {p: [] for p in desktop_order}
    mobile_series: dict[str, list[float]] = {p: [] for p in mobile_order}

    for month_key in month_keys:
        desktop_totals = monthly_desktop[month_key]
        desktop_total = sum(desktop_totals.values())
        for platform in desktop_order:
            if desktop_total:
                pct = desktop_totals[platform] / desktop_total * 100
            else:
                pct = 0.0
            desktop_series[platform].append(pct)

        mobile_totals = monthly_mobile[month_key]
        mobile_total = sum(mobile_totals.values())
        for platform in mobile_order:
            if mobile_total:
                pct = mobile_totals[platform] / mobile_total * 100
            else:
                pct = 0.0
            mobile_series[platform].append(pct)

    return dates, desktop_series, mobile_series


def latest_snapshot(
    records: list,
    os_to_platform: dict,
    exclude_set: set,
    desktop_order: list[str],
    mobile_order: list[str],
) -> tuple[str, dict[str, float], dict[str, float]]:
    """Compute platform shares for the most recent complete month."""
    month_keys = sorted({r["date"][:7] for r in records})
    if not month_keys:
        return "", {}, {}

    latest_month = month_keys[-1]
    desktop_totals = defaultdict(int)
    mobile_totals = defaultdict(int)

    for record in records:
        if record["date"][:7] != latest_month:
            continue
        os_name = record["os"]
        if os_name in exclude_set:
            continue
        category_platform = os_to_platform.get(os_name)
        if not category_platform:
            continue

        category, platform = category_platform
        visits = int(record.get("visits", 0))
        if category == "desktop":
            desktop_totals[platform] += visits
        else:
            mobile_totals[platform] += visits

    desktop_total = sum(desktop_totals.values())
    mobile_total = sum(mobile_totals.values())

    desktop_pct = {
        p: (desktop_totals[p] / desktop_total * 100 if desktop_total else 0.0)
        for p in desktop_order
    }
    mobile_pct = {
        p: (mobile_totals[p] / mobile_total * 100 if mobile_total else 0.0)
        for p in mobile_order
    }

    return latest_month, desktop_pct, mobile_pct


def plot_platforms(
    dates: list[datetime],
    series: dict[str, list[float]],
    order: list[str],
    colors: dict[str, str],
    title: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(12, 5))

    for platform in order:
        ax.plot(
            dates,
            series[platform],
            label=platform,
            color=colors[platform],
            linewidth=2,
        )

    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylabel("Share of category (%)")
    ax.set_ylim(0, 100)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(mdates.MonthLocator(interval=6))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def format_table(platforms: list[str], shares: dict[str, float]) -> str:
    lines = ["| Platform | Share |", "| --- | ---: |"]
    for platform in platforms:
        lines.append(f"| {platform} | {shares[platform]:.1f}% |")
    return "\n".join(lines)


def write_readme(
    data_range: tuple[str, str],
    latest_month: str,
    desktop_order: list[str],
    mobile_order: list[str],
    desktop_pct: dict[str, float],
    mobile_pct: dict[str, float],
) -> None:
    start, end = data_range
    content = f"""*This README is auto-generated. Do not edit manually — changes will be overwritten.*

# Platform Share on USA.gov

Monthly desktop and mobile platform usage based on [DAP (Digital Analytics Program)](https://digital.gov/guides/dap/) OS visit data.

See [`analysis/os_filter.json`](analysis/os_filter.json) for which desktop platforms are included and excluded.

**Data range:** {start} to {end}

## Desktop platforms

![Desktop platform share over time](assets/desktop-platforms.png)

### Latest month ({latest_month})

{format_table(desktop_order, desktop_pct)}

## Mobile platforms

![Mobile platform share over time](assets/mobile-platforms.png)

### Latest month ({latest_month})

{format_table(mobile_order, mobile_pct)}

## Regenerate locally

```bash
pip install -r requirements.txt
python analysis/generate_readme.py
```
"""
    README_FILE.write_text(content, encoding="utf-8")


def main() -> None:
    filt = load_filter()
    desktop_order = platform_order(filt, "desktop")
    mobile_order = platform_order(filt, "mobile")
    desktop_colors = platform_colors(filt, "desktop")
    mobile_colors = platform_colors(filt, "mobile")
    os_to_platform = build_os_to_platform(filt)
    exclude_set = set(filt["exclude"])

    print("Loading data...")
    records = collect_all_records()
    print(f"  {len(records):,} records loaded.")

    warn_unknown_os(records, os_to_platform, exclude_set)

    dates, desktop_series, mobile_series = aggregate_monthly(
        records, os_to_platform, exclude_set, desktop_order, mobile_order
    )
    if not dates:
        sys.exit("ERROR: No data to plot.")

    data_start = dates[0].strftime("%Y-%m")
    data_end = dates[-1].strftime("%Y-%m")
    latest_month, desktop_pct, mobile_pct = latest_snapshot(
        records, os_to_platform, exclude_set, desktop_order, mobile_order
    )

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating graphs...")
    plot_platforms(
        dates,
        desktop_series,
        desktop_order,
        desktop_colors,
        "Desktop Platform Share on USA.gov",
        ASSETS_DIR / "desktop-platforms.png",
    )
    plot_platforms(
        dates,
        mobile_series,
        mobile_order,
        mobile_colors,
        "Mobile Platform Share on USA.gov",
        ASSETS_DIR / "mobile-platforms.png",
    )

    write_readme(
        (data_start, data_end),
        latest_month,
        desktop_order,
        mobile_order,
        desktop_pct,
        mobile_pct,
    )

    print(f"  Wrote {ASSETS_DIR / 'desktop-platforms.png'}")
    print(f"  Wrote {ASSETS_DIR / 'mobile-platforms.png'}")
    print(f"  Wrote {README_FILE}")


if __name__ == "__main__":
    main()
