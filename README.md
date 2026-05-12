## ファイル共有 Web アプリ

ブラウザからファイルをアップロードし、共有リンク・一覧表示・ダウンロードページを提供する aiohttp ベースのWebアプリです。

### 主な機能
- 複数ファイルのWebアップロード
- 共有リンク、個別ダウンロードページ、プレビュー表示
- 認証付きファイル一覧
- 複数ファイルのまとめページとZIPダウンロード

## 必要環境
- Python 3.10 以降
- pip / venv
- 任意: `.env` でのカスタム環境変数

## セットアップ
1. 仮想環境を作成・有効化
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
2. 依存パッケージをインストール
   ```bash
   pip install -r requirements.txt
   ```
3. ファイル一覧にログインが必要な場合は `listing_credentials.json` を用意するか、`LISTING_USERNAME` / `LISTING_PASSWORD` を設定

## 起動と停止
```bash
python bot.py
```

起動すると以下が動作します。
- アップローダー UI/API: `HTTP_HOST:HTTP_PORT`、初期値 `0.0.0.0:8000`
- 公開ファイル一覧: `HTTP_LISTING_PORT`、初期値 `8004`
- ログインページ: `HTTP_LOGIN_PORT`、初期値 `8080`

停止する場合は Ctrl+C で終了してください。

## Web UI と認証
- `uploads/` に保存されたファイルは `website/` 以下のテンプレートをもとに配信されます。
- 認証は `listing_credentials.json`（`{"users": [{"username": "...", "password": "..."}]}`）または `LISTING_USERNAME` / `LISTING_PASSWORD` で設定します。
- ログイン後は自動更新付きの一覧 (`website/listing.html`) へ遷移し、検索・プレビュー・ダウンロードが可能です。

## 設定
`.env` もしくは環境変数で下記を上書きできます。

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `HTTP_HOST` / `HTTP_PORT` | `0.0.0.0` / `8000` | アップローダー UI/API の待ち受け |
| `HTTP_LISTING_PORT` | `8004` | 公開一覧 UI のポート |
| `HTTP_LOGIN_PORT` | `8080` | ログインページのポート |
| `ENABLE_UPLOAD_SERVER` / `ENABLE_LISTING_SERVER` | `1` / `1` | アップローダー/一覧サーバーの起動制御（`0` で無効化） |
| `MAX_UPLOAD_BYTES` | `5GB` | 単一ファイルのアップロード上限 |
| `MAX_IP_STORAGE_BYTES` | `~80GB` | 同一 IP の累計アップロード上限 (`0` で無効) |
| `PUBLIC_BASE_URL` | `https://upload.dongurihub.jp` | 一覧で表示する公開 URL |
| `LISTING_HOME_URL` | `/` | リンク切れ時に戻る URL |
| `LISTING_USERNAME` / `LISTING_PASSWORD` | なし | 基本認証を単一ユーザーで固定する場合に指定 |
| `LISTING_CREDENTIALS_FILE` | `listing_credentials.json` | 複数ユーザーの認証情報ファイル |
| `LISTING_SESSION_SECRET` | ランダム生成 | ログインセッション署名キー |
| `LISTING_SESSION_TTL` | `43200` (12h) | セッション有効期限（秒） |
| `EXTERNAL_URL` | なし | 外部公開 URL（必要なら設定） |

`.env` の例:
```env
HTTP_HOST=0.0.0.0
HTTP_PORT=8000
HTTP_LISTING_PORT=8004
LISTING_SESSION_SECRET=change_me
PUBLIC_BASE_URL=https://upload.example.com
```

## ファイル構成
- `bot.py`: Webサーバーのエントリーポイント
- `config.py`: ルートディレクトリやポート設定の共通ヘルパー
- `file_index.py`: `file_index.json` への読み書き
- `helpers.py`: ファイルサイズ変換やテンプレート描画などのユーティリティ
- `web_server.py`: アップロード API と一覧 UI を提供する aiohttp アプリ
- `website/`: HTML/CSS/JS テンプレート
- `uploads/`: 受信ファイルの保存先。起動時に自動作成されます。
- `listing_credentials.json`: ファイル一覧用の認証情報

## 補足
- 依存パッケージを追加したら `requirements.txt` を更新してください。
- Web UI の見た目や挙動は `website/assets/*.css`, `website/assets/*.js` で調整できます。
- 大容量ファイルを扱う場合は `MAX_UPLOAD_BYTES` と `MAX_IP_STORAGE_BYTES` を必ず再設定してください。
