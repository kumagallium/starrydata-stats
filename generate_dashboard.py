# /// script
# requires-python = ">=3.9"
# dependencies = ["pandas>=1.3"]
# ///
"""集計結果 (output/) から単一 HTML のダッシュボードを生成する。

最新の output/snapshot_YYYY-MM-DD/ と output/history.csv を読み込み、
dashboard_template.html にデータを埋め込んで dashboard.html を出力する。
生成された HTML は自己完結しており、ブラウザで開くだけで閲覧できる。

使い方:
    python generate_dashboard.py        # 通常は aggregate_stats.py から自動で呼ばれる
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

TOP_N_DASH = 10  # ダッシュボードのランキング系チャートに表示する件数


def latest_snapshot_dir(output_dir: Path) -> Path:
    dirs = sorted(output_dir.glob("snapshot_*"))
    if not dirs:
        sys.exit(f"エラー: {output_dir}/snapshot_* が見つかりません。先に aggregate_stats.py を実行してください。")
    return dirs[-1]


def records(path: Path, head: int = 0) -> list:
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

    info_cats = pd.read_csv(snap_dir / "sample_info_categories.csv")

    def cat_top(descriptor: str, n: int = TOP_N_DASH) -> list:
        df = info_cats[info_cats["descriptor"] == descriptor].head(n)
        return df[["category", "samples"]].to_dict(orient="records")

    data = {
        "snapshot": summary.get("snapshot", ""),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": summary,
        "monthly": monthly,
        "yearly": yearly,
        "by_project": records(snap_dir / "by_project.csv"),
        "by_property": records(snap_dir / "curves_by_property_y.csv", head=TOP_N_DASH),
        "journals": records(snap_dir / "papers_by_journal.csv", head=TOP_N_DASH),
        "compositions": records(snap_dir / "top_compositions.csv", head=TOP_N_DASH),
        "sample_info_descriptors": records(snap_dir / "sample_info_descriptors.csv", head=12),
        "fabrication": cat_top("FabricationProcess"),
        "material_family": cat_top("MaterialFamily"),
        "form": cat_top("Form"),
        "history": records(output_dir / "history.csv"),
    }

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    # </script> 等でスクリプトが途切れないようエスケープして埋め込む
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("/*__DATA_JSON__*/", payload, 1)
    dashboard_path.write_text(html, encoding="utf-8")
    return dashboard_path


if __name__ == "__main__":
    path = generate_dashboard()
    print(f"ダッシュボードを生成しました: {path}")
