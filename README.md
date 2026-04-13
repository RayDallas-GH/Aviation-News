# Aviation-News

Aviation Wire の RSS から、キーワードで絞り込んだ記事を **`items.json`** に書き出し、**AVIATION NEWS** ダッシュボード HTML（**3カラム**: JAL グループ / ANA グループ / 独立系・LCC）を生成します。GitHub Actions で定期実行し、GitHub Pages で公開できます。

公開 URL（Pages 有効後）: https://raydallas-gh.github.io/Aviation-News/

## ローカル実行

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export OUT_DIR=public
python fetcher.py && python renderer.py
```

`public/index.html` をブラウザで開いてください。

## ダッシュボードの内容

- **ヘッダー**: サイト名、最終更新時刻（ビルド時刻の JST）、「自動更新 5分」表記、総記事数とグループ別件数、カテゴリ用セレクト。
- **上段**: JAL / ANA / 独立系・LCC の3カラム。両方のグループにマッチする記事は **JAL 列と ANA 列の両方に表示** されます（重複表示）。各列では、タイトル（なければ要約先頭）に **`feeds.yaml` の該当グループキーワードで最初に当たった語**を `items.json` の `badge_jal` / `badge_ana` / `badge_oth` として保存し、**社名バッジ**として表示します。
- **バッジ**: `feeds.yaml` の **`breaking_keywords`** に一致すると **BREAKING**（列内で先頭付近にソート）。**`category_keywords`** で路線・財務・機材・国際線・その他を付与。
- **カテゴリフィルター**: 静的 HTML のため、ブラウザ上のスクリプトで `.news-row` の表示を切り替えます（「全カテゴリ」以外では、該当カテゴリが付いていない行は隠れます）。
- **自動更新 5分**: `index.html` に `<meta http-equiv="refresh" content="300">` があり、5分ごとにページを再読み込みします。表示内容そのものは **GitHub Actions のビルド結果** までしか更新されません（再読込で取得できるのは直近デプロイ済みの静的ファイルです）。
- **下段**: 那覇発着のお得情報テーブル。データはリポジトリ直下の **`deals.json`**（手動メンテ想定）。`renderer.py` がビルド時に `OUT_DIR/deals.json` へコピーします。見出し中黒の代わりに **`DEALS_SECTION_MARK`**（デフォルトは島 🏝️ の絵文字）を表示します。飛行機に戻す場合は `renderer.py` 内の定数を `"🛫"` などに変更してください。

## `feeds.yaml`

- **`feeds`**: RSS の URL 一覧。
- **`keyword_groups`**: `jal` / `ana` / `oth` など。いずれかにマッチした記事だけ `items.json` に載ります。キーワードは YAML で数値と解釈されないよう **機材コード等はクォート推奨**（未クォートでもフェッチャー側で文字列化します）。
- **`category_keywords`**: 各記事の `categories`（表示・フィルター用）。任意省略可。
- **`breaking_keywords`**: `breaking: true` と BREAKING バッジ。省略時は `BREAKING` / `速報` / `緊急` を使用。

## `deals.json`

ルートの `deals.json` の `deals` 配列に、エアライン名・任意の **`airline_url`**（公式サイト。指定時は名前が新しいタブで開くリンクになる）・ドット色・`status`（`active` / `none`）・セール名・終了日（`MM/DD` 表記の文字列）を並べます。**掲載内容は自動取得せず、正確性は編集者の確認に依存します。** ファイルが無い場合でもビルドは成功し、テーブルに案内文が出ます。

## GitHub Pages

1. **Settings → Pages → Build and deployment → Source** を **GitHub Actions** にする（**先にこれを有効にしないとデプロイが失敗**します）。
2. コードを `main` に push する。

または、先に push した場合は、上記の Pages 設定を **GitHub Actions** にしたうえで、**Actions** から **Daily aviation report** を **Re-run** します。ワークフローが成功すると、上記の GitHub Pages URL に公開されます（初回は数分かかることがあります）。
