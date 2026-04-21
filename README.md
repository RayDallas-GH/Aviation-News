# Aviation-News

Aviation Wire の RSS から、キーワードで絞り込んだ記事を **`items.json`** に書き出し、**AVIATION NEWS** ダッシュボード HTML（**Airline news**: 国内3カラム＋海外エアライン、**お得情報**、**メーカー・モビリティ**3列）を生成します。GitHub Actions で定期実行し、GitHub Pages で公開できます。

公開 URL（Pages 有効後）: https://raydallas-gh.github.io/Aviation-News/

## ローカル実行

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export OUT_DIR=public
python fetcher.py && python industry_fetcher.py && python deals_fetcher.py && python renderer.py
```

`public/index.html` をブラウザで開いてください。お得情報だけ試す場合は `python deals_fetcher.py && python renderer.py`（`items.json` が既にある前提）でも構いません。メーカー列を含め試す場合は `items.json` に加え `python industry_fetcher.py` が必要です。

## ダッシュボードの内容

- **ヘッダー**: サイト名、最終更新時刻（ビルド時刻の JST）、総記事数とグループ別件数（国内3＋海外エアライン）、カテゴリ用セレクト。
- **Airline news**: 見出し **国内エアライン** の下に JAL / ANA / 独立系・LCC の3カラム、その下に見出し **海外エアライン** と1ブロック（横幅は **JAL+ANA の2列分**）。複数グループにマッチする記事は **該当する列すべてに表示** されます（重複表示）。各列では、タイトル（なければ要約先頭）に **`feeds.yaml` の該当グループキーワードで最初に当たった語**を `badge_jal` / `badge_ana` / `badge_oth` / `badge_intl_air` として保存し、**社名バッジ**として表示します。
- **バッジ**: `feeds.yaml` の **`breaking_keywords`** に一致すると **BREAKING**（列内で先頭付近にソート）。**`category_keywords`** で路線・財務・機材・国際線・その他を付与。
- **カテゴリフィルター**: 静的 HTML のため、ブラウザ上のスクリプトで `.news-row` の表示を切り替えます（「全カテゴリ」以外では、該当カテゴリが付いていない行は隠れます）。
- **メーカー・モビリティ**（Airline news の直下）: **[industry_feeds.yaml](industry_feeds.yaml)** に従い **`industry_fetcher.py`** が Aviation Wire の RSS を読み、**日系メーカー / 海外メーカー / 空飛ぶクルマ**の3列に振り分けて **`public/industry_news.json`** を生成します。1記事は **`match_order`**（既定: AAM → 海外 → 日系）で先に当たった列だけに入ります。`renderer.py` が `industry_news.json` を読み込み表示します。当面は **Aviation Wire のみ**（`feeds` に URL を追加すれば他ソースも同じフェッチャーで取り込み可能）。
- **那覇発着お得情報**（ページ最下段のセクション）: テーブル（**エアライン（TOP） / セール（取得元URL） / ステータス / 終了日**の4列・コンパクト表示）。**`deals_fetcher.py`** が **[deals_sources.yaml](deals_sources.yaml)** の `campaign_url` を取得し、各行に **`campaign_url`** を書き込み、本文から **終了日（MM/DD）** を推定します。**終了済みでも、ページから取れた販売締切があれば表示**します（ステータスは `none` のまま）。**開催中**は **終了日が取れ、かつ今日以降の締切で、セール系の語がタイトルまたは本文に当たるときだけ**。ヒューリスティックのため **公式と必ず一致するとは限りません**。**`OUT_DIR/deals.json`** に **`fetched_at`**（取得時刻）付きで書きます。`renderer.py` は **`public/deals.json` を優先**し、無いときだけリポジトリの **`deals.json`** を読み、それも無ければ `deals.json` を `public/` にコピーします。テーブル直下に **反映時刻**を表示します。見出しの区切りは **`DEALS_SECTION_MARK`**（デフォルトは島 🏝️）です。

## `feeds.yaml`

- **`feeds`**: RSS の URL 一覧。
- **`keyword_groups`**: `jal` / `ana` / `oth` / **`intl_air`（海外主要航空会社）** など。いずれかにマッチした記事だけ `items.json` に載ります。キーワードは YAML で数値と解釈されないよう **機材コード等はクォート推奨**（未クォートでもフェッチャー側で文字列化します）。
- **`category_keywords`**: 各記事の `categories`（表示・フィルター用）。任意省略可。
- **`breaking_keywords`**: `breaking: true` と BREAKING バッジ。省略時は `BREAKING` / `速報` / `緊急` を使用。

## `industry_feeds.yaml` と `industry_fetcher.py`

メーカー・eVTOL ニュースは **`fetcher.py`（航空会社向け）とは別パイプライン**です。`fetcher.py` は `keyword_groups`（jal/ana/oth/intl_air）に当たった記事を `items.json` に載せます。機体メーカー単独の記事は本パイプラインで拾います。

- **`feeds`**: RSS の URL（フェーズ1は Aviation Wire 1 本。**後続**で Flight Global 等の公式・他メディア RSS を `feeds` に行追加すれば、同じ `industry_fetcher.py` がマージ取得します）。
- **`match_order`**: 1記事が複数トラックの `include` に当たるとき、**先に書いたトラックだけ**に入れる（既定 **`aam` → `intl_oem` → `jp_oem`**）。空飛ぶクルマ系を海外 OEM より優先するための順序です。
- **`tracks`**: 内部 ID と表示名・キーワード・件数上限。
  | トラック ID | 表示（`label_ja`） | 上限目安 | 内容の目安 |
  |-------------|-------------------|---------|------------|
  | `jp_oem` | 日系メーカー | 8 | 三菱重工・川重・IHI 等、日系の航空機・エンジン・機体関連（`include` に **三菱重工** を必ず含める） |
  | `intl_oem` | 海外メーカー | 8 | Boeing / Airbus / Embraer 等 |
  | `aam` | 空飛ぶクルマ | 12 | SkyDrive / Joby / eVTOL / UAM 等。記事数が少ない想定で **キーワードは広め**（YAML で随時追加） |
- **`exclude`**: 記事タイトル＋要約に一致したら **メーカー・モビリティの全トラックから** スキップ（任意）。**`feeds.yaml` の `intl_air` と同じ外航名**を並べ、エアライン向けニュースが OEM 列に入らないようにする（Airline news の海外列で表示）。

**出力**: `public/industry_news.json`（`generated_at`、`tracks[]` に `id` / `label_ja` / `items[]`。各 `items` 要素は `track` / `title` / `link` / `published` / `source_id` / `source_name`）。

## GitHub Actions のビルド順

[`.github/workflows/daily-report.yml`](.github/workflows/daily-report.yml) の **Fetch and render** は次の順で実行します（`OUT_DIR=public`）。

1. `fetcher.py` → `public/items.json`（Airline news 国内＋海外エアライン用）
2. `industry_fetcher.py` → `public/industry_news.json`（お得情報の**直下**に表示するメーカー3カラム用。**`renderer.py` より前**に必須）
3. `deals_fetcher.py` → `public/deals.json`
4. `renderer.py` → `public/index.html`
5. `notify_email.py`（任意）→ 前回ビルド時のスナップショット（`notify_state.json`、Actions の cache）と `items.json` / `industry_news.json` のリンクを比較し、**新規 URL があるときだけ**メール送信

## 新着メール通知（任意・テスト向け）

GitHub Actions のシークレットを設定すると、**自分宛**に「RSS 由来の新着記事」だけをテキストメールで送れます。

### API キー・秘密情報の取り扱い

- **リポジトリに API キーを書かない**（`feeds.yaml` やワークフローへの直書きは禁止）。
- **GitHub**: `Settings → Secrets and variables → Actions` にだけ保存し、ワークフローは `secrets.*` で参照。
- **ローカル**: リポジトリ直下に **`.env`** を置く（**`.gitignore` で除外済み**）。雛形は **[`.env.example`](.env.example)** をコピーして `.env` にリネームし、値だけ記入。`notify_email.py` は起動時に `.env` を読みます（**既にシェルや CI で設定されている変数は上書きしません**）。
- 漏えいしたキーは **Resend 側でローテーション（無効化・再発行）** を検討してください。

- **初回実行**: ベースラインのリンク集合を保存し、**メールは送りません**（2回目以降から差分通知）。
- **送信方法**: **Resend**（`RESEND_API_KEY`）または **SMTP**（`SMTP_HOST` など）。どちらも未設定ならスナップショットだけ更新し、送信はスキップします。
- **推奨シークレット（Resend）**: `RESEND_API_KEY`、`NOTIFY_EMAIL_TO`（受信）、`NOTIFY_EMAIL_FROM`（送信元。テストは Resend の `onboarding@resend.dev` などドキュメントに従う）。
- **SMTP の例**: `SMTP_HOST`、`SMTP_PORT`（既定 587）、`SMTP_USER`、`SMTP_PASSWORD`、`NOTIFY_EMAIL_FROM`、`NOTIFY_EMAIL_TO`。
- **無効化**: リポジトリシークレット `NOTIFY_EMAIL_DISABLED=true`、またはワークフローから `notify_email.py` の行を外す。

ローカルで試すと `notify_state.json` が作られるので、**`.gitignore` に含め済み**です（コミット不要）。

### はじめての方へ（用語の整理）

このあとの説明で出てくる言葉の意味です（入社直後でも追いやすいように）。

- **RSS**: ニュースサイトが配信する「新着記事の一覧データ」です。プログラムがこれを読み、タイトル・**URL**（記事1本を指すインターネット上の住所）・公開日時を取ります。
- **ビルド**: 決まった手順でプログラムを動かし、そのときのデータからページ（HTML）を作り直す作業です。ここでは **GitHub Actions**（GitHub がクラウド上で自動実行してくれる仕組み）が、1日2回などの予定でビルドします。
- **スナップショット（`notify_state.json`）**: 「前回までにシステムが把握していた記事 URL の一覧」を保存したメモです。次のビルドで「一覧に無かった新しい URL があるか」を見て、メールに載せるか決めます。
- **シークレット（Secrets）**: API キーやメールの受信先など、ソースコードに直接書けない情報を GitHub に安全に預ける機能です。**設定されていないとメール送信がスキップ**されます。
- **Resend / SMTP**: メールを実際に送るためのサービス・仕組みです。どちらかを設定しないと、プログラムは「送る先が無い」と判断します。

### メール未着のとき（ヘッダー「最終更新」との違い）

- **ヘッダーの「最終更新」**は [`fetcher.py`](fetcher.py) が `items.json` に書く **`generated_at`**（そのビルドで RSS 取得が最後まで成功した時刻の JST 表示）です。新着件数に関係なく、**ビルドが成功するたびに進みます**。
- **各記事カードの時刻**（「07:00」「昨日」など）は RSS の **公開日時**であり、メールの「新着」判定とは別です。
- **メール**は [`notify_email.py`](notify_email.py) が **`items.json` と `industry_news.json` の URL** を、Actions の cache が保持する **`notify_state.json`** と比較し、**前回に無かった URL があるときだけ**送ります。ダッシュボードに記事が出ていても、**その URL がすでにスナップショットに含まれていれば**メールは出ません（前日夜のビルドや手動 Re-run で先に取り込まれた場合など）。

**届かないときの確認**

1. **GitHub**: リポジトリの **Actions → Daily aviation report** を開き、該当実行の **Fetch, render, notify** ステップのログで次を探します。  
   - `notify_email: no new links` → 新規 URL なし（仕様どおり送信なし）  
   - `notify_email: sent via Resend` または SMTP 成功メッセージ → 送信済み（受信トレイ・迷惑メール・Resend ダッシュボードを確認）  
   - `NOTIFY_EMAIL_TO unset; skipping send` または API キー未設定メッセージ → **Settings → Secrets and variables → Actions** に `NOTIFY_EMAIL_TO`（および Resend なら `RESEND_API_KEY` / `NOTIFY_EMAIL_FROM`）が設定されているか確認してください。
2. **初回実行**はベースライン保存のみでメールは送りません（2 回目以降から差分通知）。

## `deals_sources.yaml`（自動）

- 各行: `airline`, `dot`, `airline_url`（社名リンク）, **`campaign_url`**（セール情報を読みに行く URL）, **`sale_abbr`**（セール列リンク表記「◯◯セール」用。例: `JAL`, `ソラシド`, `Peach`, `JJP`）。
- **販売終了日**は「～◯月◯日（曜）23:59」「予約・販売期間：…～◯月◯日」「◯/◯（曜）09:59まで」などをヒューリスティックに解析し、**搭乗期間**の行と紛らわしい候補は落とし気味です（ページによっては未取得・誤検出があり得ます）。
- サイトの HTML 変更でパースが外れることがあります。取得元を変える場合は `campaign_url` を公式のキャンペーン一覧などに差し替えてください。

## `deals.json`（フォールバック）

- **`deals_fetcher.py` を実行しない**、または **`public/deals.json` が無い** ときに `renderer.py` が読みます（手動メンテ用）。
- フィールドは `airline`, `airline_url`, `dot`, `campaign_url`, `sale_abbr`, `status`, `end_date`（`sale_name` は互換のため空文字で残す場合があります）。`sale_abbr` が無いときはセール列は「セール」と表示。

## お得情報の更新タイミング

- 公開ページのお得情報は **`index.html` に焼き込み**で、**GitHub Actions が成功するたび**にだけ更新されます。テーブル直下の **「お得情報の反映」**に、`public/deals.json` の **`fetched_at`**（`deals_fetcher` 実行時刻・JST 表示）が出ます。リポジトリの `deals.json` のみを使っている場合は、ヘッダーと同じビルド時刻にフォールバックします。
- **定期ビルド**は UTC **11:00 と 23:00**（JST では同日 **20:00** 頃と、日付が変わったあとの **08:00** 頃）の **1 日 2 回**です。その間は表示内容は変わりません。
- 更新されているのに古いままに見えるときは、ブラウザの **強制再読込**（キャッシュ無視のリロード）を試してください。

## GitHub Pages

1. **Settings → Pages → Build and deployment → Source** を **GitHub Actions** にする（**先にこれを有効にしないとデプロイが失敗**します）。
2. コードを `main` に push する。

または、先に push した場合は、上記の Pages 設定を **GitHub Actions** にしたうえで、**Actions** から **Daily aviation report** を **Re-run** します。ワークフローが成功すると、上記の GitHub Pages URL に公開されます（初回は数分かかることがあります）。
