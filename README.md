# Starrydata データセット集計ツール

[Starrydata2](https://www.starrydata2.org/) の公開データセット(papers / samples / curves)を、
さまざまな観点でデータ数集計するツールです。データは日々更新されるため、
Google Drive の共有フォルダから実行時点の最新データを自動取得して集計できます。
集計結果は単一 HTML のダッシュボード (`dashboard.html`) でも閲覧できます。

## セットアップ

[uv](https://docs.astral.sh/uv/) があれば追加のセットアップは不要です(依存を自動解決)。
pip を使う場合は次でインストールします:

```bash
pip install -r requirements.txt   # pandas, gdown
```

## 使い方

```bash
# 最新データを Google Drive から取得してから集計(推奨・普段使いはこれ1コマンド)
uv run aggregate_stats.py --download

# 手元の starrydata_dataset/ をそのまま集計
uv run aggregate_stats.py

# データ取得のみ
uv run download_dataset.py

# ダッシュボードの再生成のみ(集計済みの output/ から)
uv run generate_dashboard.py
```

pip 環境の場合は `uv run` を `python` に読み替えてください。
集計後に `dashboard.html` をブラウザで開くと、サマリ・成長グラフ・各種ランキングを閲覧できます。

## 集計内容

コンソールに主要サマリを表示し、以下のファイルを出力します。

### `output/snapshot_YYYY-MM-DD/`(スナップショット日付ごとに保存)

| ファイル | 内容 |
|---|---|
| `summary.json` | 全体サマリ(登録論文数・データが紐づく論文数・サンプル数・カーブ数・データ点数・図の数・ユニークDOI/組成数・1論文あたり平均など) |
| `by_project.csv` | プロジェクト別(熱電・電池・磁性など14種)の論文数・カーブ数・データ点数 |
| `curves_by_property_y.csv` | 物性(prop_y)別のカーブ数・データ点数 |
| `curves_by_property_pair.csv` | 物性の組み合わせ(prop_x × prop_y)別のカーブ数・データ点数 |
| `registrations_by_year.csv` | 登録年別の論文/サンプル/カーブ数(累積つき) |
| `registrations_by_month.csv` | 登録月別の論文/サンプル/カーブ数(累積つき) |
| `papers_by_issued_year.csv` | 論文の出版年別の論文数 |
| `papers_by_journal.csv` | ジャーナル別論文数(上位50) |
| `papers_by_publisher.csv` | 出版社別論文数(上位50) |
| `top_compositions.csv` | 組成別サンプル数(上位50) |
| `sample_info_descriptors.csv` | sample_info(JSON)の descriptor 別記入状況(合成プロセス・形状などの記入数) |
| `sample_info_categories.csv` | sample_info の descriptor × category 別サンプル数(FabricationProcess / Form / MaterialFamily など全 descriptor) |

### `output/history.csv`(スナップショット横断の推移記録)

実行のたびに、そのスナップショット日付の主要件数(論文・サンプル・カーブ・データ点数など)を
1 行追記します(同じ日付は上書き)。定期的に `--download` 付きで実行すると、
データベースの成長を時系列で追跡できます。

### `dashboard.html`(単一 HTML ダッシュボード)

集計実行のたびに自動再生成されます。ブラウザで開くだけで閲覧でき(サーバー不要・自己完結)、
以下を表示します。ライト/ダークモード両対応です。

- 主要件数の KPI タイル(データが紐づく論文数・サンプル・カーブ・データ点・図・ユニーク組成)
- データベースの成長(累積登録数の月次ライングラフ)
- 年別の新規登録数(グループ棒グラフ)
- プロジェクト別・物性別・ジャーナル別・組成別ランキング(横棒グラフ)
- サンプル詳細情報(sample_info)の記入状況と、合成プロセス・材料ファミリー・形状の内訳
- スナップショット推移(history.csv の成長グラフ。実行を重ねると蓄積)

各チャートはホバーで詳細値を表示し、「表で見る」から同じデータを表形式でも確認できます。

## データ取得の仕組み

- 取得元: [Google Drive 共有フォルダ](https://drive.google.com/drive/folders/1OVMP7j61CJFwLtJ-qZFef9ko40Othayh)(公開フォルダのため認証不要)
- フォルダ内の zip(現在は `starrydata_dataset.zip` 1つ)を検出してダウンロードします。
  ファイル名が変わっても、フォルダ内の zip を探すため追従できます。
- zip の検証・展開に成功してから既存の `starrydata_dataset/` を置き換えるため、
  ダウンロード失敗で手元のデータが壊れることはありません。
- ダウンロードした zip は原本として `starrydata_dataset.zip` に保存(上書き)します。

## ファイル構成

```
.
├── aggregate_stats.py      # 集計本体(--download で最新取得込み)
├── download_dataset.py     # Google Drive から最新データ取得
├── generate_dashboard.py   # dashboard.html の生成(集計時に自動実行)
├── dashboard_template.html # ダッシュボードのテンプレート
├── dashboard.html          # 生成されたダッシュボード(自動生成)
├── requirements.txt
├── starrydata_dataset/     # データセット(自動生成・git 管理外)
│   ├── starrydata_papers.csv
│   ├── starrydata_samples.csv
│   ├── starrydata_curves.csv
│   ├── db_snapshot.txt     # スナップショット日時
│   └── README.md           # データセット本体の説明
└── output/                 # 集計結果(自動生成)
    ├── history.csv
    └── snapshot_YYYY-MM-DD/
```

データセット本体 (`starrydata_dataset/`, `starrydata_dataset.zip`) はサイズが大きいため
git 管理外です。クローン後は `uv run aggregate_stats.py --download` で取得してください。

## 集計観点の追加方法

`aggregate_stats.py` は観点ごとに `aggregate_*` 関数に分かれています。
新しい観点を追加する場合は、関数を 1 つ追加して `main()` の `outputs` 辞書に
出力ファイル名とともに登録してください。
