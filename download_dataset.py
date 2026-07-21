# /// script
# requires-python = ">=3.9"
# dependencies = ["gdown>=5"]
# ///
"""Fetch and extract the latest Starrydata dataset from the shared Google Drive folder.

Downloads the zip file in the shared folder (normally a single
starrydata_dataset.zip) and extracts it into starrydata_dataset/. The existing
data is only replaced after the archive has been verified and extracted, so a
failed download never corrupts the local copy.

Usage:
    python download_dataset.py    # fetch and extract the latest dataset
    uv run download_dataset.py    # with uv (dependencies resolved automatically)
"""

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Shared Google Drive folder that holds the latest Starrydata dataset.
FOLDER_ID = "1OVMP7j61CJFwLtJ-qZFef9ko40Othayh"

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "starrydata_dataset"
DEFAULT_ZIP_PATH = BASE_DIR / "starrydata_dataset.zip"


def download_latest(
    data_dir: Path = DEFAULT_DATA_DIR,
    zip_path: Path = DEFAULT_ZIP_PATH,
) -> Path:
    """Download the latest zip from the shared folder and extract it into data_dir.

    Returns:
        Path of the extraction directory.
    """
    import gdown  # deferred so aggregation-only runs do not require gdown

    print(f"Listing the Google Drive folder ({FOLDER_ID})...")
    entries = gdown.download_folder(id=FOLDER_ID, skip_download=True, quiet=True)
    if not entries:
        sys.exit("Error: could not list the folder. Check the sharing settings and URL.")

    zips = [e for e in entries if e.path.lower().endswith(".zip")]
    if not zips:
        names = ", ".join(e.path for e in entries)
        sys.exit(f"Error: no zip file found in the folder. Contents: {names}")

    # If several zips exist, take the last one in name order (date-stamped names expected).
    zips.sort(key=lambda e: e.path)
    target = zips[-1]
    if len(zips) > 1:
        print(f"Note: {len(zips)} zip files found; using '{target.path}'.")
        for e in zips:
            print(f"  - {e.path}")

    with tempfile.TemporaryDirectory(prefix="starrydata_") as tmp:
        tmp_dir = Path(tmp)
        tmp_zip = tmp_dir / "dataset.zip"

        print(f"Downloading '{target.path}'...")
        result = gdown.download(id=target.id, output=str(tmp_zip), quiet=False)
        if result is None or not tmp_zip.exists():
            sys.exit("Error: download failed.")

        print("Verifying and extracting the zip...")
        extract_dir = tmp_dir / "extracted"
        try:
            with zipfile.ZipFile(tmp_zip) as zf:
                bad = zf.testzip()
                if bad is not None:
                    sys.exit(f"Error: corrupted zip (first bad file: {bad})")
                zf.extractall(extract_dir)
        except zipfile.BadZipFile:
            sys.exit("Error: the downloaded file is not a valid zip archive.")

        # Replace the existing data only after a successful extraction.
        if data_dir.exists():
            shutil.rmtree(data_dir)
        shutil.move(str(extract_dir), str(data_dir))

        # Keep the latest zip as the pristine copy (replacing any previous one).
        shutil.move(str(tmp_zip), str(zip_path))

    snapshot = data_dir / "db_snapshot.txt"
    if snapshot.exists():
        print(f"Done: extracted into {data_dir} (snapshot: {snapshot.read_text().strip()})")
    else:
        print(f"Done: extracted into {data_dir}")
    return data_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and extract the latest Starrydata dataset from Google Drive"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"extraction directory (default: {DEFAULT_DATA_DIR.name}/)",
    )
    args = parser.parse_args()
    download_latest(data_dir=args.data_dir)


if __name__ == "__main__":
    main()
