# /// script
# requires-python = ">=3.9"
# dependencies = ["pandas>=1.3", "gdown>=5"]
# ///
"""Aggregate the Starrydata dataset from multiple angles.

Reads the three CSVs (papers / samples / curves) in starrydata_dataset/ and
produces an overall summary plus per-project, per-property, and per-period
breakdowns, printed to the console and written as CSV / JSON files.

Usage:
    python aggregate_stats.py               # aggregate the local starrydata_dataset/
    python aggregate_stats.py --download    # fetch the latest data from Google Drive first
    uv run aggregate_stats.py --download    # with uv (dependencies resolved automatically)

Outputs:
    output/snapshot_YYYY-MM-DD/  per-snapshot CSVs and summary.json
    output/history.csv           one row of headline counts per snapshot (time series)
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

TOP_N = 50  # number of rows to keep in ranking CSVs

# Every element symbol, used by the periodic-table element aggregation.
ELEMENT_SYMBOLS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar",
    "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr",
    "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe",
    "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu",
    "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn",
    "Fr", "Ra", "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr",
    "Rf", "Db", "Sg", "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
}

# Battery-style acronyms that appear verbatim in the composition column.
# Excluded so their letters are not misread as element symbols (e.g. SIB -> S/I/B).
# Extend this set as new entries show up in top_compositions.csv.
KNOWN_ABBREVIATIONS = {
    "LMB", "RMB", "SIB", "PIB", "ZIB", "AIB", "LIB", "LAB",
    "ASSLSB", "ASSLB", "ASSSLSB", "PANI", "NAS", "YBCO",
    "undefined", "Unknown",
}

# Non-element substrings stripped from composition strings before tokenizing
# (e.g. the leftovers of "MWCNTs"/"MWNTs" would otherwise be misread as W or Ts).
COMPOSITION_NOISE = re.compile(r"MWCNTs?|SWCNTs?|DWCNTs?|MWNTs?|SWNTs?|DWNTs?|CNTs?|TsO|Not identified")

# One capital + optional lowercase letter. A token followed by another lowercase
# letter (except x/y/z) is treated as the start of an English word and rejected
# (e.g. "Po" in "Polyaniline", "He" in "half-Heusler"). x/y/z are allowed because
# they are common stoichiometry variables, as in "Bi(x)Sb(2-x)".
ELEMENT_TOKEN = re.compile(r"[A-Z][a-z]?(?![a-w])")


# ---------------------------------------------------------------------------
# Loading and parsing
# ---------------------------------------------------------------------------

def parse_created_at(s: pd.Series) -> pd.Series:
    """Parse 'Thu Jan 25 2018 13:56:56 GMT+0900 (Japan Standard Time)' timestamps.

    Every row in the dataset uses GMT+0900 (JST), so only the leading datetime
    part is extracted and treated as JST local time.
    """
    return pd.to_datetime(s.str.slice(4, 24), format="%b %d %Y %H:%M:%S", errors="coerce")


def clean_quoted(s: pd.Series) -> pd.Series:
    """Strip quotes embedded in the value itself, as in '\"Journal Name\"'."""
    return s.fillna("").str.strip().str.strip('"').str.strip()


def parse_project_names(s: pd.Series) -> pd.Series:
    """Parse '["A","B"]'-style JSON arrays into Python lists."""

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
    """Count data points in the x column's JSON array strings '[1.2,3.4,...]'.

    The arrays contain only numbers, so comma count + 1 equals the length.
    Empty arrays and missing values count as 0.
    """
    x = x.fillna("").str.strip()
    n = x.str.count(",") + 1
    n[x.isin(["", "[]"])] = 0
    return n.astype("int64")


def load_dataset(data_dir: Path):
    """Read the three CSVs (needed columns only) and return parsed DataFrames."""
    papers_path = data_dir / "starrydata_papers.csv"
    samples_path = data_dir / "starrydata_samples.csv"
    curves_path = data_dir / "starrydata_curves.csv"
    for p in (papers_path, samples_path, curves_path):
        if not p.exists():
            sys.exit(
                f"Error: {p} not found. "
                "Run with --download, or fetch the latest data with download_dataset.py."
            )

    print(f"Loading dataset: {data_dir}/")

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

    # Publication year: extracted from the issued column '{"date_parts":[[2014,4,15]]}'
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
    """Read the snapshot timestamp string from db_snapshot.txt."""
    p = data_dir / "db_snapshot.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def snapshot_date(snapshot: str) -> str:
    """Extract YYYY-MM-DD from the snapshot string (falls back to today)."""
    m = re.search(r"\d{4}-\d{2}-\d{2}", snapshot)
    if m:
        return m.group(0)
    return pd.Timestamp.today().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------

def aggregate_summary(papers, samples, curves, snapshot: str) -> dict:
    """Return the overall summary (headline counts) as a dict."""
    # figure_id is a global identifier: a figure referenced by curves from
    # several papers counts once. This matches the official stats page
    # (starrydata.github.io/starrydata_datasets).
    n_figures = int(curves["figure_id"].dropna().nunique())
    per_paper_samples = samples.groupby("SID").size()
    per_paper_curves = curves.groupby("SID").size()

    # Registered papers that actually have samples or curves attached,
    # counted as unique SIDs (papers.csv contains a few duplicated SID rows).
    sids_with_data = set(samples["SID"].dropna()) | set(curves["SID"].dropna())
    papers_with_data = len(set(papers["SID"].dropna()) & sids_with_data)

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
    """Paper, curve, and data-point counts per project."""
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
    """Curve and data-point counts per property (prop_y alone and prop_x x prop_y pairs)."""
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
    """Registration counts per period based on created_at. freq='YS' (year) or 'MS' (month)."""
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
    # Cumulative columns, used to track database growth.
    for name in ("papers", "samples", "curves"):
        out[f"{name}_cum"] = out[name].cumsum()
    return out.reset_index()


def aggregate_papers_meta(papers) -> tuple:
    """Paper counts by publication year, journal, and publisher."""
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
    """Aggregate completion and category distributions from sample_info (JSON).

    sample_info has the shape {descriptor: {category, comment, extracted}} and
    holds details such as the fabrication process (FabricationProcess), form
    (Form), and material family (MaterialFamily).
    """
    desc_filled = Counter()      # rows where any of category/comment/extracted is filled
    desc_with_cat = Counter()    # rows where a category is selected
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
    """Sample counts per composition (top TOP_N)."""
    comp = samples["composition"].fillna("").str.strip()
    return (
        comp[comp != ""].to_frame("composition").groupby("composition").size()
        .rename("samples").sort_values(ascending=False).head(TOP_N).reset_index()
    )


def aggregate_elements(samples) -> pd.DataFrame:
    """Count samples per chemical element appearing in composition strings.

    An element repeated within one sample still counts once (i.e. "number of
    samples containing the element"). Separators such as the "|" in "Li|S" are
    ignored by the tokenizer, so no special handling is needed.
    """
    counts = Counter()
    for comp in samples["composition"].dropna().astype(str):
        comp = comp.strip()
        if not comp or comp in KNOWN_ABBREVIATIONS:
            continue
        comp = COMPOSITION_NOISE.sub(" ", comp)
        for sym in set(ELEMENT_TOKEN.findall(comp)):
            if sym in ELEMENT_SYMBOLS:
                counts[sym] += 1
    return pd.DataFrame(
        sorted(counts.items(), key=lambda kv: -kv[1]),
        columns=["element", "samples"],
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def update_history(output_dir: Path, summary: dict) -> None:
    """Upsert the snapshot's headline counts into output/history.csv."""
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


def print_table(df: pd.DataFrame, n: int, title: str, show_top: bool = True) -> None:
    """Pretty-print the top n rows to the console."""
    suffix = f" (top {n})" if show_top else ""
    print(f"\n## {title}{suffix}")
    shown = df.head(n).copy()
    for col in shown.select_dtypes("number").columns:
        shown[col] = shown[col].map("{:,}".format)
    print(shown.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate the Starrydata dataset")
    parser.add_argument(
        "--download", action="store_true",
        help="fetch the latest dataset from Google Drive before aggregating",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help=f"dataset directory (default: {DEFAULT_DATA_DIR.name}/)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"output directory (default: {DEFAULT_OUTPUT_DIR.name}/)",
    )
    args = parser.parse_args()

    if args.download:
        from download_dataset import download_latest
        download_latest(data_dir=args.data_dir)
        print()

    papers, samples, curves = load_dataset(args.data_dir)
    snapshot = read_snapshot(args.data_dir)

    # --- aggregate ---
    summary = aggregate_summary(papers, samples, curves, snapshot)
    by_project = aggregate_by_project(papers, curves)
    by_prop_y, by_prop_pair = aggregate_by_property(curves)
    by_year = aggregate_by_period(papers, samples, curves, freq="YS")
    by_month = aggregate_by_period(papers, samples, curves, freq="MS")
    by_issued, journals, publishers = aggregate_papers_meta(papers)
    compositions = aggregate_compositions(samples)
    elements = aggregate_elements(samples)
    info_descriptors, info_categories = aggregate_sample_info(samples)

    # --- write files ---
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
        "elements.csv": elements,
        "sample_info_descriptors.csv": info_descriptors,
        "sample_info_categories.csv": info_categories,
    }
    for name, df in outputs.items():
        df.to_csv(out_dir / name, index=False)

    update_history(args.output_dir, summary)

    # --- console report ---
    line = "=" * 64
    print(f"\n{line}\n Starrydata dataset aggregation  (snapshot: {snapshot or 'unknown'})\n{line}")
    print("\n## Summary")
    labels = [
        ("Registered papers", "papers"),
        ("Papers with data", "papers_with_data"),
        ("Samples", "samples"),
        ("Curves", "curves"),
        ("Data points", "data_points"),
        ("Figures", "figures"),
        ("Unique DOIs", "unique_dois_in_papers"),
        ("Unique compositions", "unique_compositions_in_samples"),
    ]
    for label, key in labels:
        print(f"  {label:<20}: {summary[key]:>12,}")
    print(f"  {'Per paper':<20}: samples mean {summary['samples_per_paper_mean']} / "
          f"curves mean {summary['curves_per_paper_mean']}")
    print(f"  {'Per curve':<20}: data points mean {summary['points_per_curve_mean']}")

    print_table(by_project, 14, "By project")
    print_table(by_prop_y, 10, "Curves by property (prop_y)")
    print_table(info_descriptors, 10, "sample_info completion by descriptor")
    print_table(by_year.tail(6).reset_index(drop=True), 6,
                "Registrations by year (last 6; *_cum = cumulative)", show_top=False)

    print(f"\nResults saved to: {out_dir}/")
    print(f"History: {args.output_dir / 'history.csv'}")

    from generate_dashboard import generate_dashboard
    dash = generate_dashboard(output_dir=args.output_dir)
    print(f"Dashboard: {dash} (open in a browser)")


if __name__ == "__main__":
    main()
