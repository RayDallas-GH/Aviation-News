# Aviation-News

Aviation Wire の RSS から、キーワードで絞り込んだ記事を **`items.json`** に書き出し、**AVIATION NEWS** ダッシュボード HTML（**3カラム**: JAL グループ / ANA グループ / 独立系・LCC）を生成します。GitHub Actions で定期実行し、GitHub Pages で公開できます。

公開 URL（Pages 有効後）: https://raydallas-gh.github.io/Aviation-News/

## ローカル実行

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export OUT_DIR=public
python fetcher.py && python deals_fetcher.py && python renderer.py
```

`public/index.html` をブラウザで開いてください。お得情報だけ試す場合は `python deals_fetcher.py && python renderer.py`（`items.json` が既にある前提）でも構いません。

## ダッシュボードの内容

- **ヘッダー**: サイト名、最終更新時刻（ビルド時刻の JST）、「自動更新 5分」表記、総記事数とグループ別件数、カテゴリ用セレクト。
- **上段**: JAL / ANA / 独立系・LCC の3カラム。両方のグループにマッチする記事は **JAL 列と ANA 列の両方に表示** されます（重複表示）。各列では、タイトル（なければ要約先頭）に **`feeds.yaml` の該当グループキーワードで最初に当たった語**を `items.json` の `badge_jal` / `badge_ana` / `badge_oth` として保存し、**社名バッジ**として表示します。
- **バッジ**: `feeds.yaml` の **`breaking_keywords`** に一致すると **BREAKING**（列内で先頭付近にソート）。**`category_keywords`** で路線・財務・機材・国際線・その他を付与。
- **カテゴリフィルター**: 静的 HTML のため、ブラウザ上のスクリプトで `.news-row` の表示を切り替えます（「全カテゴリ」以外では、該当カテゴリが付いていない行は隠れます）。
- **自動更新 5分**: `index.html` に `<meta http-equiv="refresh" content="300">` があり、5分ごとにページを再読み込みします。表示内容そのものは **GitHub Actions のビルド結果** までしか更新されません（再読込で取得できるのは直近デプロイ済みの静的ファイルです）。
- **下段**: 那覇発着のお得情報テーブル（**エアライン / ステータス / 終了日**の3列）。**`deals_fetcher.py`** が **[deals_sources.yaml](deals_sources.yaml)** の `campaign_url` を取得し、本文から日付表現を探して **終了日（MM/DD）** と **`active` / `none`** を推定します。**開催中**は **終了日が取れ、かつ今日以降の締切で、セール系の語がタイトルまたは本文に当たるときだけ**（終了日が空のまま開催中にならないようにしています）。判定にはページタイトルも参照します。ヒューリスティックのため **公式と必ず一致するとは限りません**。**`OUT_DIR/deals.json`** に **`fetched_at`**（取得時刻）付きで書きます。`renderer.py` は **`public/deals.json` を優先**し、無いときだけリポジトリの **`deals.json`** を読み、それも無ければ `deals.json` を `public/` にコピーします。テーブル直下に **反映時刻**を表示します。見出しの区切りは **`DEALS_SECTION_MARK`**（デフォルトは島 🏝️）です。

## `feeds.yaml`

- **`feeds`**: RSS の URL 一覧。
- **`keyword_groups`**: `jal` / `ana` / `oth` など。いずれかにマッチした記事だけ `items.json` に載ります。キーワードは YAML で数値と解釈されないよう **機材コード等はクォート推奨**（未クォートでもフェッチャー側で文字列化します）。
- **`category_keywords`**: 各記事の `categories`（表示・フィルター用）。任意省略可。
- **`breaking_keywords`**: `breaking: true` と BREAKING バッジ。省略時は `BREAKING` / `速報` / `緊急` を使用。

## `deals_sources.yaml`（自動）

- 各行: `airline`, `dot`, `airline_url`（社名リンク）, **`campaign_url`**（セール情報を読みに行く URL）。
- **販売終了日**は「～◯月◯日（曜）23:59」「予約・販売期間：…～◯月◯日」「◯/◯（曜）09:59まで」などをヒューリスティックに解析し、**搭乗期間**の行と紛らわしい候補は落とし気味です（ページによっては未取得・誤検出があり得ます）。
- サイトの HTML 変更でパースが外れることがあります。取得元を変える場合は `campaign_url` を公式のキャンペーン一覧などに差し替えてください。

## `deals.json`（フォールバック）

- **`deals_fetcher.py` を実行しない**、または **`public/deals.json` が無い** ときに `renderer.py` が読みます（手動メンテ用）。
- フィールドは `airline`, `airline_url`, `dot`, `status`, `end_date`（`sale_name` は互換のため空文字で残す場合があります）。

## お得情報の更新タイミング

- 公開ページのお得情報は **`index.html` に焼き込み**で、**GitHub Actions が成功するたび**にだけ更新されます。テーブル直下の **「お得情報の反映」**に、`public/deals.json` の **`fetched_at`**（`deals_fetcher` 実行時刻・JST 表示）が出ます。リポジトリの `deals.json` のみを使っている場合は、ヘッダーと同じビルド時刻にフォールバックします。
- **定期ビルド**は UTC **11:00 と 23:00**（JST では同日 **20:00** 頃と、日付が変わったあとの **08:00** 頃）の **1 日 2 回**です。その間は表示内容は変わりません。
- 更新されているのに古いままに見えるときは、ブラウザの **強制再読込**（キャッシュ無視のリロード）を試してください。

## GitHub Pages

1. **Settings → Pages → Build and deployment → Source** を **GitHub Actions** にする（**先にこれを有効にしないとデプロイが失敗**します）。
2. コードを `main` に push する。

または、先に push した場合は、上記の Pages 設定を **GitHub Actions** にしたうえで、**Actions** から **Daily aviation report** を **Re-run** します。ワークフローが成功すると、上記の GitHub Pages URL に公開されます（初回は数分かかることがあります）。
