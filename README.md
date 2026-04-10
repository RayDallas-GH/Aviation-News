# Aviation-News

Aviation Wire の RSS から、JAL / ANA 関連記事をキーワードで絞り込み、HTML レポートを生成します。GitHub Actions で毎日実行し、GitHub Pages で公開できます。

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

## GitHub Pages

1. **Settings → Pages → Build and deployment → Source** を **GitHub Actions** にする（**先にこれを有効にしないとデプロイが失敗**します）。
2. コードを `main` に push する。

または

1. 先に push した場合は、上記の Pages 設定を **GitHub Actions** にしたうえで、**Actions** から **Daily aviation report** を **Re-run** する。

3. ワークフローが成功すると、上記の GitHub Pages URL に公開されます（初回は数分かかることがあります）。

キーワードは `feeds.yaml` の `keywords` を編集してください。
