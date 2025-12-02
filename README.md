## Discord アップローダー Bot

Discord サーバーからファイルを受け取り、Web UI で配布・管理できるボットです。Slash Command で認証ユーザーを追加し、ブラウザからのアップロード／一覧表示／ダウンロードを一括で提供します。

### 主な機能
- Discord でのファイル投稿とメタデータ管理
- aiohttp ベースのアップローダー UI/API
- 認証付きの公開ファイル一覧・ログインページ
- GitHub README 取得やプレビュー生成などのユーティリティ

---

## 必要環境
- Python 3.10 以降
- pip / venv
- Discord Bot Token（`token.txt` に保存）
- （任意）`.env` でのカスタム環境変数

---

## セットアップ
1. リポジトリを取得
   ```bash
   git clone https://github.com/kokorodonguri/bot.git
   cd bot
   ```
2. 仮想環境を作成・有効化
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. 依存パッケージをインストール
   ```bash
   pip install -r requirements.txt
   ```
4. `token.txt` を作成し、Discord Bot Token を 1 行で保存
5. 環境変数を `.env` に記述（例は下記「設定」参照）
6. ファイル一覧にログインが必要な場合は `listing_credentials.json` を用意するか、後述の `/adduser` コマンドで登録

---

## 起動と停止
```
python bot.py
```

起動すると以下がまとめて動作します。
- Discord Bot（Slash Command, Message ハンドリング）
- アップローダー UI/API（`HTTP_HOST:HTTP_PORT`、初期値 `0.0.0.0:8000`）
- 公開ファイル一覧（`HTTP_LISTING_PORT`、初期値 `8004`）
- ログインページ（`HTTP_LOGIN_PORT`、初期値 `8080`）

`web_server.py` などで Web サーバーを別プロセスとして動かす場合は、`.env` で `ENABLE_UPLOAD_SERVER=0` や `ENABLE_LISTING_SERVER=0` を設定するとボット側でのポート待ち受けをスキップできます。

停止する場合はプロセスを Ctrl+C で終了してください。

---

## Web UI と認証
- `uploads/` に保存されたファイルは `website/` 以下のテンプレートをもとに配信されます。
- 認証は `listing_credentials.json`（`{"users": [{"username": "...", "password": "..."}]}`）または `LISTING_USERNAME` / `LISTING_PASSWORD` で設定します。
- Discord から追加する場合は `/adduser <username> <password>` を実行すると `listing_credentials.json` に追記され、即時反映されます。
- ログイン後は自動更新付きの一覧 (`website/listing.html`) へ遷移し、検索・プレビュー・ダウンロードが可能です。

---

## 設定
`.env` もしくは環境変数で下記を上書きできます。

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `HTTP_HOST` / `HTTP_PORT` | `0.0.0.0` / `8000` | アップローダー UI/API の待ち受け |
| `HTTP_LISTING_PORT` | `8004` | 公開一覧 UI のポート |
| `HTTP_LOGIN_PORT` | `8080` | ログインページのポート |
| `ENABLE_UPLOAD_SERVER` / `ENABLE_LISTING_SERVER` | `1` / `1` | 内蔵のアップローダー/一覧サーバーの起動制御（`0` で無効化） |
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

---

## ファイル構成
- `bot.py`: Discord Bot と Web サーバーのエントリーポイント
- `config.py`: ルートディレクトリやポート設定の共通ヘルパー
- `discord_setup.py`: Slash Command / イベント登録、Web サーバーの起動制御
- `file_index.py`: `file_index.json` への読み書きとトークン管理
- `github_client.py`: GitHub README を取得する非同期クライアント
- `helpers.py`: ファイルサイズ変換やテンプレート描画などのユーティリティ
- `web_server.py`: アップロード API と一覧 UI を提供する aiohttp アプリ
- `website/`: HTML/CSS/JS テンプレート（`listing.html`, `assets/`, `login/` など）
- `uploads/`: 受信ファイルの保存先。ボット起動時に自動作成されます。
- `listing_credentials.json`: ファイル一覧用の認証情報

---

## Discord コマンド
- `/adduser <username> <password>`: ログイン可能なユーザーを追加
- その他の Slash Command / メッセージハンドラは `discord_setup.py` を参照してください。

---

## 補足
- 依存パッケージを追加したら `requirements.txt` を更新してください。
- Web UI の見た目や挙動は `website/assets/*.css`, `website/assets/*.js` で調整できます。
- 大容量ファイルを扱う場合は `MAX_UPLOAD_BYTES` と `MAX_IP_STORAGE_BYTES` を必ず再設定してください。
