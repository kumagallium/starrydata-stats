# /// script
# requires-python = ">=3.9"
# dependencies = ["pandas>=1.3", "gdown>=5"]
# ///
"""Starrydata データセットをさまざまな観点で集計する。

starrydata_dataset/ 内の papers / samples / curves の 3 つの CSV を読み込み、
全体サマリ・プロジェクト別・物性別・年別推移などを集計して、
コンソール表示と CSV / JSON ファイル出力を行う。

使い方:
    python aggregate_stats.py               # 手元の starrydata_dataset/ を集計
    python aggregate_stats.py --download    # Google Drive から最新を取得してから集計
    uv run aggregate_stats.py --download    # uv を使う場合(依存を自動解決)

出力:
    output/snapshot_YYYY-MM-DD/  に各集計 CSV と summary.json
    output/history.csv           にスナップショットごとの主要件数を追記(推移の記録)
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "starrydata_dataset"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"

TOP_N = 50  # ランキング系 CSV に出力する上位件数


# ---------------------------------------------------------------------------
# 読み込みとパース
# ---------------------------------------------------------------------------

def parse_created_at(s: pd.Series) -> pd.Series:
    """'Thu Jan 25 2018 13:56:56 GMT+0900 (Japan Standard Time)' 形式をパースする。

    タイムゾーンは全行 GMT+0900 (JST) であることを確認済みのため、
    先頭の日時部分のみを取り出して JST のローカル時刻として扱う。
    """
    return pd.to_datetime(s.str.slice(4, 24), format="%b %d %Y %H:%M:%S", errors="coerce")


def clean_quoted(s: pd.Series) -> pd.Series:
    """'\"Journal Name\"' のように値自体に付いた引用符を除去する。"""
    return s.fillna("").str.strip().str.strip('"').str.strip()


def parse_project_names(s: pd.Series) -> pd.Series:
    """'["A","B"]' 形式の JSON 配列をリストにパースする。"""

    def parse_one(v):
        if not isinstance(v, str) or not v.strip():
            return []
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []

    return s.map(parse_one)


def count_points(x: pd.Series) -> pd.Series:
    """x 列の JSON 配列文字列 '[1.2,3.4,...]' からデータ点数を数える。

    数値のみの配列なのでカンマの数 + 1 が要素数。空配列・欠損は 0。
    """
    x = x.fillna("").str.strip()
    n = x.str.count(",") + 1
    n[x.isin(["", "[]"])] = 0
    return n.astype("int64")


def load_dataset(data_dir: Path):
    """3 つの CSV を必要な列だけ読み込み、パース済みの DataFrame を返す。"""
    papers_path = data_dir / "starrydata_papers.csv"
    samples_path = data_dir / "starrydata_samples.csv"
    curves_path = data_dir / "starrydata_curves.csv"
    for p in (papers_path, samples_path, curves_path):
        if not p.exists():
            sys.exit(
                f"エラー: {p} が見つかりません。"
                "--download を付けて実行するか、download_dataset.py で最新データを取得してください。"
            )

    print(f"データを読み込んでいます: {data_dir}/")

    papers = pd.read_csv(
        papers_path,
        encoding="utf-8-sig",
        usecols=["SID", "DOI", "issued", "container_title", "publisher",
                 "project_names", "created_at"],
        dtype=str,
    )
    samples = pd.read_csv(
        samples_path,
        encoding="utf-8-sig",
        usecols=["sample_id", "composition", "SID", "DOI", "created_at", "sample_info"],
        dtype=str,
    )
    curves = pd.read_csv(
        curves_path,
        encoding="utf-8-sig",
        usecols=["SID", "sample_id", "figure_id", "prop_x", "prop_y",
                 "x", "created_at", "project_names"],
        dtype=str,
    )

    papers["created_dt"] = parse_created_at(papers["created_at"])
    samples["created_dt"] = parse_created_at(samples["created_at"])
    curves["created_dt"] = parse_created_at(curves["created_at"])

    # 論文の出版年: issued 列 '{"date_parts":[[2014,4,15]]}' から年を抽出
    papers["issued_year"] = (
        papers["issued"].fillna("").str.extract(r"\[\[(\d{4})", expand=False)
    )

    papers["journal"] = clean_quoted(papers["container_title"])
    papers["publisher_clean"] = clean_quoted(papers["publisher"])

    papers["projects"] = parse_project_names(papers["project_names"])
    curves["projects"] = parse_project_names(curves["project_names"])

    curves["prop_x"] = clean_quoted(curves["prop_x"])
    curves["prop_y"] = clean_quoted(curves["prop_y"])
    curves["n_points"] = count_points(curves["x"])

    return papers, samples, curves


def read_snapshot(data_dir: Path) -> str:
    """db_snapshot.txt からスナップショット日時文字列を読む。"""
    p = data_dir / "db_snapshot.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def snapshot_date(snapshot: str) -> str:
    """スナップショット文字列から YYYY-MM-DD を取り出す(無ければ今日の日付)。"""
    m = re.search(r"\d{4}-\d{2}-\d{2}", snapshot)
    if m:
        return m.group(0)
    return pd.Timestamp.today().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 各種集計
# ---------------------------------------------------------------------------

def aggregate_summary(papers, samples, curves, snapshot: str) -> dict:
    """全体サマリ(件数系)を dict で返す。"""
    n_figures = curves.dropna(subset=["figure_id"]).groupby(["SID", "figure_id"]).ngroups
    per_paper_samples = samples.groupby("SID").size()
    per_paper_curves = curves.groupby("SID").size()

    # 登録論文のうち、サンプルまたはカーブのデータが実際に紐づいている論文数
    sids_with_data = set(samples["SID"].dropna()) | set(curves["SID"].dropna())
    papers_with_data = int(papers["SID"].isin(sids_with_data).sum())

    return {
        "snapshot": snapshot,
        "papers": int(len(papers)),
        "papers_with_data": papers_with_data,
        "samples": int(len(samples)),
        "curves": int(len(curves)),
        "data_points": int(curves["n_points"].sum()),
        "figures": int(n_figures),
        "unique_dois_in_papers": int(papers["DOI"].dropna().nunique()),
        "unique_compositions_in_samples": int(
            samples["composition"].fillna("").str.strip().replace("", pd.NA).nunique()
        ),
        "samples_per_paper_mean": round(float(per_paper_samples.mean()), 2),
        "samples_per_paper_median": float(per_paper_samples.median()),
        "samples_per_paper_max": int(per_paper_samples.max()),
        "curves_per_paper_mean": round(float(per_paper_curves.mean()), 2),
        "curves_per_paper_median": float(per_paper_curves.median()),
        "curves_per_paper_max": int(per_paper_curves.max()),
        "points_per_curve_mean": round(float(curves["n_points"].mean()), 2),
    }


def aggregate_by_project(papers, curves) -> pd.DataFrame:
    """プロジェクト別の論文数・カーブ数・データ点数。"""
    p = (
        papers[["SID", "projects"]].explode("projects").dropna(subset=["projects"])
        .groupby("projects").size().rename("papers")
    )
    c_exploded = curves[["projects", "n_points"]].explode("projects").dropna(subset=["projects"])
    c = c_exploded.groupby("projects").agg(
        curves=("n_points", "size"), data_points=("n_points", "sum")
    )
    df = pd.concat([p, c], axis=1).fillna(0).astype("int64")
    df.index.name = "project"
    return df.sort_values("curves", ascending=False).reset_index()


def aggregate_by_property(curves) -> tuple:
    """物性別(prop_y 単独、および prop_x × prop_y の組)のカーブ数・データ点数。"""
    by_y = (
        curves.groupby("prop_y")
        .agg(curves=("n_points", "size"), data_points=("n_points", "sum"))
        .sort_values("curves", ascending=False)
        .reset_index()
    )
    by_pair = (
        curves.groupby(["prop_x", "prop_y"])
        .agg(curves=("n_points", "size"), data_points=("n_points", "sum"))
        .sort_values("curves", ascending=False)
        .reset_index()
    )
    return by_y, by_pair


def aggregate_by_period(papers, samples, curves, freq: str) -> pd.DataFrame:
    """登録日時ベースの期間別件数。freq='YS'(年) または 'MS'(月)。"""
    fmt = "%Y" if freq == "YS" else "%Y-%m"
    parts = []
    for name, df in (("papers", papers), ("samples", samples), ("curves", curves)):
        s = (
            df.dropna(subset=["created_dt"])
            .set_index("created_dt")
            .resample(freq).size().rename(name)
        )
        parts.append(s)
    out = pd.concat(parts, axis=1, sort=True).fillna(0).astype("int64")
    out.index = out.index.strftime(fmt)
    out.index.name = "period"
    # 累積列(データベースの成長を追うため)
    for name in ("papers", "samples", "curves"):
        out[f"{name}_cum"] = out[name].cumsum()
    return out.reset_index()


def aggregate_papers_meta(papers) -> tuple:
    """出版年別・ジャーナル別・出版社別の論文数。"""
    by_issued = (
        papers.dropna(subset=["issued_year"]).groupby("issued_year").size()
        .rename("papers").reset_index().rename(columns={"issued_year": "year"})
        .sort_values("year")
    )
    journals = (
        papers.loc[papers["journal"] != ""].groupby("journal").size()
        .rename("papers").sort_values(ascending=False).head(TOP_N).reset_index()
    )
    publishers = (
        papers.loc[papers["publisher_clean"] != ""].groupby("publisher_clean").size()
        .rename("papers").sort_values(ascending=False).head(TOP_N).reset_index()
        .rename(columns={"publisher_clean": "publisher"})
    )
    return by_issued, journals, publishers


def aggregate_sample_info(samples) -> tuple:
    """sample_info (JSON) から descriptor 別の記入状況とカテゴリ分布を集計する。

    sample_info は {descriptor: {category, comment, extracted}} 形式。
    合成プロセス (FabricationProcess) や形状 (Form)、材料ファミリー
    (MaterialFamily) などの情報がここに含まれる。
    """
    desc_filled = Counter()      # category/comment/extracted のいずれかが記入されている数
    desc_with_cat = Counter()    # category が選択されている数
    cat_counts = defaultdict(Counter)

    for v in samples["sample_info"].dropna():
        try:
            d = json.loads(v)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        for k, obj in d.items():
            k2 = k.strip()
            if not k2 or not isinstance(obj, dict):
                continue
            cat = str(obj.get("category") or "").strip()
            com = str(obj.get("comment") or "").strip()
            ext = str(obj.get("extracted") or "").strip()
            if cat or com or ext:
                desc_filled[k2] += 1
            if cat:
                desc_with_cat[k2] += 1
                cat_counts[k2][cat] += 1

    descriptors = pd.DataFrame(
        [(k, n, desc_with_cat.get(k, 0)) for k, n in desc_filled.most_common()],
        columns=["descriptor", "samples_filled", "samples_with_category"],
    )
    categories = pd.DataFrame(
        [(k, val, n) for k, counter in cat_counts.items() for val, n in counter.most_common()],
        columns=["descriptor", "category", "samples"],
    ).sort_values(["descriptor", "samples"], ascending=[True, False]).reset_index(drop=True)
    return descriptors, categories


def aggregate_compositions(samples) -> pd.DataFrame:
    """組成別のサンプル数(上位 TOP_N 件)。"""
    comp = samples["composition"].fillna("").str.strip()
    return (
        comp[comp != ""].to_frame("composition").groupby("composition").size()
        .rename("samples").sort_values(ascending=False).head(TOP_N).reset_index()
    )


# ---------------------------------------------------------------------------
# 出力
# ---------------------------------------------------------------------------

def update_history(output_dir: Path, summary: dict) -> None:
    """スナップショットごとの主要件数を output/history.csv に upsert する。"""
    history_path = output_dir / "history.csv"
    cols = ["snapshot_date", "papers", "samples", "curves", "data_points",
            "figures", "unique_dois_in_papers", "unique_compositions_in_samples"]
    row = {c: summary.get(c) for c in cols[1:]}
    row["snapshot_date"] = snapshot_date(summary["snapshot"])

    if history_path.exists():
        hist = pd.read_csv(history_path, dtype={"snapshot_date": str})
        hist = hist[hist["snapshot_date"] != row["snapshot_date"]]
        hist = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
    else:
        hist = pd.DataFrame([row])
    hist = hist[cols].sort_values("snapshot_date")
    hist.to_csv(history_path, index=False)


def pad_label(label: str, width: int) -> str:
    """全角文字を幅 2 として label を width 相当まで空白で埋める。"""
    import unicodedata
    w = sum(2 if unicodedata.east_asian_width(ch) in "FWA" else 1 for ch in label)
    return label + " " * max(width - w, 0)


def print_table(df: pd.DataFrame, n: int, title: str, show_top: bool = True) -> None:
    """上位 n 行を整形してコンソール表示する。"""
    suffix = f" (上位{n}件)" if show_top else ""
    print(f"\n■ {title}{suffix}")
    shown = df.head(n).copy()
    for col in shown.select_dtypes("number").columns:
        shown[col] = shown[col].map("{:,}".format)
    print(shown.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Starrydata データセットの各種集計")
    parser.add_argument(
        "--download", action="store_true",
        help="集計前に Google Drive から最新データセットを取得する",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help=f"データセットのディレクトリ (default: {DEFAULT_DATA_DIR.name}/)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"集計結果の出力先 (default: {DEFAULT_OUTPUT_DIR.name}/)",
    )
    args = parser.parse_args()

    if args.download:
        from download_dataset import download_latest
        download_latest(data_dir=args.data_dir)
        print()

    papers, samples, curves = load_dataset(args.data_dir)
    snapshot = read_snapshot(args.data_dir)

    # --- 集計 ---
    summary = aggregate_summary(papers, samples, curves, snapshot)
    by_project = aggregate_by_project(papers, curves)
    by_prop_y, by_prop_pair = aggregate_by_property(curves)
    by_year = aggregate_by_period(papers, samples, curves, freq="YS")
    by_month = aggregate_by_period(papers, samples, curves, freq="MS")
    by_issued, journals, publishers = aggregate_papers_meta(papers)
    compositions = aggregate_compositions(samples)
    info_descriptors, info_categories = aggregate_sample_info(samples)

    # --- ファイル出力 ---
    out_dir = args.output_dir / f"snapshot_{snapshot_date(snapshot)}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    outputs = {
        "by_project.csv": by_project,
        "curves_by_property_y.csv": by_prop_y,
        "curves_by_property_pair.csv": by_prop_pair,
        "registrations_by_year.csv": by_year,
        "registrations_by_month.csv": by_month,
        "papers_by_issued_year.csv": by_issued,
        "papers_by_journal.csv": journals,
        "papers_by_publisher.csv": publishers,
        "top_compositions.csv": compositions,
        "sample_info_descriptors.csv": info_descriptors,
        "sample_info_categories.csv": info_categories,
    }
    for name, df in outputs.items():
        df.to_csv(out_dir / name, index=False)

    update_history(args.output_dir, summary)

    # --- コンソール表示 ---
    line = "=" * 64
    print(f"\n{line}\n Starrydata データセット集計  (snapshot: {snapshot or '不明'})\n{line}")
    print("\n■ 全体サマリ")
    labels = [
        ("登録論文数", "papers"),
        ("データあり論文数", "papers_with_data"),
        ("サンプル数", "samples"),
        ("カーブ数", "curves"),
        ("データ点数", "data_points"),
        ("図の数", "figures"),
        ("ユニークDOI数", "unique_dois_in_papers"),
        ("ユニーク組成数", "unique_compositions_in_samples"),
    ]
    for label, key in labels:
        print(f"  {pad_label(label, 16)}: {summary[key]:>12,}")
    print(f"  {pad_label('1論文あたり', 16)}: サンプル 平均{summary['samples_per_paper_mean']} / "
          f"カーブ 平均{summary['curves_per_paper_mean']}")
    print(f"  {pad_label('1カーブあたり', 16)}: データ点 平均{summary['points_per_curve_mean']}")

    print_table(by_project, 14, "プロジェクト別")
    print_table(by_prop_y, 10, "物性(prop_y)別カーブ数")
    print_table(info_descriptors, 10, "sample_info 記入状況(descriptor別)")
    print_table(by_year.tail(6).reset_index(drop=True), 6,
                "登録数の推移(直近6年、*_cum は累積)", show_top=False)

    print(f"\n結果を保存しました: {out_dir}/")
    print(f"推移の記録: {args.output_dir / 'history.csv'}")

    from generate_dashboard import generate_dashboard
    dash = generate_dashboard(output_dir=args.output_dir)
    print(f"ダッシュボード: {dash} (ブラウザで開いて閲覧)")


if __name__ == "__main__":
    main()
