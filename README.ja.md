# starrydata-stats(日本語版 README)

[![update-dashboard](https://github.com/kumagallium/starrydata-stats/actions/workflows/update-dashboard.yml/badge.svg)](https://github.com/kumagallium/starrydata-stats/actions/workflows/update-dashboard.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Starrydata](https://starrydata.org/)(無機材料科学実験データのオープンデータベース構築
プロジェクト)の Web アプリ [Starrydata2](https://www.starrydata2.org/) が公開する
データセット(papers / samples / curves)の集計ツールと、自動更新ダッシュボードです。

**公開ダッシュボード: <https://kumagallium.github.io/starrydata-stats/>**
(英語デフォルト / 日本語切替、毎日 6:00 JST に自動更新)

*English README: [README.md](README.md)*

## 何をするか

1. 公式の [Google Drive 共有フォルダ](https://drive.google.com/drive/folders/1OVMP7j61CJFwLtJ-qZFef9ko40Othayh)
   から最新データセットを**取得**(認証不要)
2. 全体サマリ・プロジェクト別・物性別・ジャーナル別・登録推移・収録元素
   (組成の周期表ヒートマップ)・sample_info の記入状況(合成プロセス・材料
   ファミリー・形状など)を**集計**
3. 自己完結の単一 HTML ダッシュボード(英/日バイリンガル)を**生成**
4. GitHub Actions で毎日 6:00 JST に「取得 → 集計 → コミット → GitHub Pages
   デプロイ」を**自動実行**

## 使い方

[uv](https://docs.astral.sh/uv/) を使う場合(依存はスクリプト内メタデータから自動解決):

```bash
uv run aggregate_stats.py --download   # 最新データ取得 → 集計 → ダッシュボード生成
```

pip の場合:

```bash
pip install -r requirements.txt        # pandas, gdown
python aggregate_stats.py --download
```

実行後、`dashboard.html` をブラウザで開いてください。個別実行:

```bash
uv run aggregate_stats.py              # 手元の starrydata_dataset/ をそのまま集計
uv run download_dataset.py             # データ取得のみ
uv run generate_dashboard.py           # 既存の output/ からダッシュボードのみ再生成
```

データセット本体(展開後 約340MB)はリポジトリに含めていません。
`--download` で必要時に取得します。

## 出力

- `output/snapshot_YYYY-MM-DD/` — スナップショットごとの集計 CSV 12 種と
  `summary.json`(内訳は [README.md](README.md#outputs) の表を参照)
- `output/history.csv` — 実行日ごとの主要件数を 1 行ずつ蓄積する実測記録。
  ダッシュボードの成長グラフは `created_at` からの再構成のため現存レコード
  しか反映されませんが、こちらは各日の実測値なので、上流データベースでの
  削除・整理も検出できます(現在ダッシュボードには表示していません。
  監査用の記録です)

## ライセンスとデータの出所

- データセットは [Starrydata プロジェクト](https://starrydata.org/) が作成・
  公開しているものです。データ自体のライセンスや引用方針はプロジェクト側に
  従ってください。
- 本リポジトリのコードは [MIT License](LICENSE) です。
