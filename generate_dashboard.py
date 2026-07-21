# /// script
# requires-python = ">=3.9"
# dependencies = ["pandas>=1.3"]
# ///
"""Generate the single-file HTML dashboard from the aggregation output (output/).

Reads the latest output/snapshot_YYYY-MM-DD/ and injects the data into
dashboard_template.html to produce dashboard.html. The generated HTML is
self-contained: opening it in a browser is all that is needed.

Usage:
    python generate_dashboard.py    # normally invoked automatically by aggregate_stats.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "dashboard_template.html"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
DASHBOARD_PATH = BASE_DIR / "dashboard.html"

TOP_N_DASH = 10  # rows to expose to the dashboard's ranking charts


def latest_snapshot_dir(output_dir: Path) -> Path:
    dirs = sorted(output_dir.glob("snapshot_*"))
    if not dirs:
        sys.exit(f"Error: no {output_dir}/snapshot_* directory found. Run aggregate_stats.py first.")
    return dirs[-1]


def records(path: Path, head: int = 0) -> list:
    if not path.exists():
        sys.exit(
            f"Error: {path} not found. "
            "The aggregation CSVs may be outdated; re-run aggregate_stats.py."
        )
    df = pd.read_csv(path)
    if head:
        df = df.head(head)
    return df.to_dict(orient="records")


def generate_dashboard(output_dir: Path = DEFAULT_OUTPUT_DIR,
                       dashboard_path: Path = DASHBOARD_PATH) -> Path:
    snap_dir = latest_snapshot_dir(output_dir)
    summary = json.loads((snap_dir / "summary.json").read_text(encoding="utf-8"))

    monthly = records(snap_dir / "registrations_by_month.csv")
    yearly = records(snap_dir / "registrations_by_year.csv")

    info_cats_path = snap_dir / "sample_info_categories.csv"
    if not info_cats_path.exists():
        sys.exit(f"Error: {info_cats_path} not found. Re-run aggregate_stats.py.")
    info_cats = pd.read_csv(info_cats_path)

    def cat_top(descriptor: str, n: int = 5, exclude: tuple = ()) -> list:
        df = info_cats[info_cats["descriptor"] == descriptor]
        if exclude:
            df = df[~df["category"].isin(exclude)]
        return df.head(n)[["category", "samples"]].to_dict(orient="records")

    data = {
        "snapshot": summary.get("snapshot", ""),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": summary,
        "monthly": monthly,
        "yearly": yearly,
        "by_project": records(snap_dir / "by_project.csv"),
        "by_property": records(snap_dir / "curves_by_property_y.csv", head=TOP_N_DASH),
        "journals": records(snap_dir / "papers_by_journal.csv", head=TOP_N_DASH),
        "elements": records(snap_dir / "elements.csv"),
        "sample_info_descriptors": records(snap_dir / "sample_info_descriptors.csv"),
        "fabrication": cat_top("FabricationProcess", exclude=("Other", "Unknown")),
        "material_family": cat_top("MaterialFamily", exclude=("Other", "Unknown")),
        "form": cat_top("Form", exclude=("Other", "Unknown")),
    }

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    # Escape "</" so the embedded JSON can never terminate the <script> element.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("/*__DATA_JSON__*/", payload, 1)
    dashboard_path.write_text(html, encoding="utf-8")
    return dashboard_path


if __name__ == "__main__":
    path = generate_dashboard()
    print(f"Dashboard generated: {path}")
