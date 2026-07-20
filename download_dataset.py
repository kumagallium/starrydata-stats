# /// script
# requires-python = ">=3.9"
# dependencies = ["gdown>=5"]
# ///
"""Google Drive の共有フォルダから最新の Starrydata データセットを取得して展開する。

共有フォルダ内の zip ファイル(通常は starrydata_dataset.zip 1つ)をダウンロードし、
starrydata_dataset/ ディレクトリに展開する。展開が成功するまで既存データは残すため、
ダウンロード失敗時に手元のデータが壊れることはない。

使い方:
    python download_dataset.py            # 最新データを取得して展開
    uv run download_dataset.py            # uv を使う場合(依存を自動解決)
"""

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Starrydata 最新データセットが置かれる Google Drive 共有フォルダ
FOLDER_ID = "1OVMP7j61CJFwLtJ-qZFef9ko40Othayh"

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "starrydata_dataset"
DEFAULT_ZIP_PATH = BASE_DIR / "starrydata_dataset.zip"


def download_latest(
    data_dir: Path = DEFAULT_DATA_DIR,
    zip_path: Path = DEFAULT_ZIP_PATH,
) -> Path:
    """共有フォルダから最新 zip をダウンロードし data_dir に展開する。

    Returns:
        展開先ディレクトリの Path
    """
    import gdown  # 集計のみの利用時に必須にしないよう遅延 import

    print(f"Google Drive フォルダ ({FOLDER_ID}) の内容を確認しています...")
    entries = gdown.download_folder(id=FOLDER_ID, skip_download=True, quiet=True)
    if not entries:
        sys.exit("エラー: フォルダの内容を取得できませんでした。共有設定や URL を確認してください。")

    zips = [e for e in entries if e.path.lower().endswith(".zip")]
    if not zips:
        names = ", ".join(e.path for e in entries)
        sys.exit(f"エラー: フォルダ内に zip ファイルが見つかりません。内容: {names}")

    # 複数 zip がある場合はファイル名の昇順で最後(日付入り名を想定)を採用
    zips.sort(key=lambda e: e.path)
    target = zips[-1]
    if len(zips) > 1:
        print(f"注意: zip が {len(zips)} 個あります。'{target.path}' を使用します。")
        for e in zips:
            print(f"  - {e.path}")

    with tempfile.TemporaryDirectory(prefix="starrydata_") as tmp:
        tmp_dir = Path(tmp)
        tmp_zip = tmp_dir / "dataset.zip"

        print(f"'{target.path}' をダウンロードしています...")
        result = gdown.download(id=target.id, output=str(tmp_zip), quiet=False)
        if result is None or not tmp_zip.exists():
            sys.exit("エラー: ダウンロードに失敗しました。")

        print("zip を検証・展開しています...")
        extract_dir = tmp_dir / "extracted"
        try:
            with zipfile.ZipFile(tmp_zip) as zf:
                bad = zf.testzip()
                if bad is not None:
                    sys.exit(f"エラー: zip が破損しています (最初の破損ファイル: {bad})")
                zf.extractall(extract_dir)
        except zipfile.BadZipFile:
            sys.exit("エラー: ダウンロードしたファイルは正しい zip ではありません。")

        # 展開に成功してから既存データを置き換える
        if data_dir.exists():
            shutil.rmtree(data_dir)
        shutil.move(str(extract_dir), str(data_dir))

        # 最新 zip を原本として保存(既存の zip は置き換え)
        shutil.move(str(tmp_zip), str(zip_path))

    snapshot = data_dir / "db_snapshot.txt"
    if snapshot.exists():
        print(f"完了: {data_dir} に展開しました (snapshot: {snapshot.read_text().strip()})")
    else:
        print(f"完了: {data_dir} に展開しました")
    return data_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Drive から最新の Starrydata データセットを取得して展開する"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"展開先ディレクトリ (default: {DEFAULT_DATA_DIR.name}/)",
    )
    args = parser.parse_args()
    download_latest(data_dir=args.data_dir)


if __name__ == "__main__":
    main()
