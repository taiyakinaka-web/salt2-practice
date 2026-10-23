# 名刺ノート

ソースコード：[taiyakinaka-web/salt2-practice](https://github.com/taiyakinaka-web/salt2-practice)

名刺画像を取り込み、AIの読み取り結果を確認・修正して保存する、1組織向けの名刺管理アプリです。氏名・会社名で検索でき、管理者が企業・部署・人物単位で閲覧範囲を設定できます。

**実装済み：** ログイン、名刺の登録・検索・詳細・元画像表示、利用者追加、閲覧許可の付与・解除、Claude接続処理。
**検証済み：** 自動テスト78件、TypeScript型チェック、本番ビルド、Chromeでの主要操作。
**未確認：** 実際のAI読み取り精度。提供キーでModels APIがHTTP 401 `authentication_error / invalid x-api-key`を返し、モデルの確認・画像送信には進めていません。

- [仕様書](docs/SPEC.md)
- [実装判断と機能の詳しい説明](docs/IMPLEMENTATION.md)
- [API仕様](docs/API.md)
- [動作確認記録](docs/VERIFICATION.md)

## 使用技術

| 部分 | 技術 |
| --- | --- |
| フロントエンド | React 19.2、TypeScript 5.9、Vite 7.3 |
| バックエンド | Python 3.12、FastAPI、SQLModel |
| 保存 | SQLite。元画像もBLOBで同じDBに保存 |
| 認証 | Argon2パスワードハッシュ、DB管理のセッションCookie |
| AI | Anthropic公式Python SDK。画像対応ClaudeのモデルIDを環境変数で指定 |
| 検証 | pytest、HTTPX、Vitest、Testing Library、TypeScript、Vite、Chrome |

対応画像は**JPEG・PNG、1枚5MiB以下、2,000万画素以下**です。画像の実データをデコードして検証します。依存関係は `frontend/package-lock.json` と `backend/requirements.lock.txt` に固定しています。

使用モデルは未確定です。接続成功後、設定したモデルIDをこの欄と動作確認記録へ追記してください。

## 起動方法（WSL Ubuntu）

確認環境はNode.js 24.15.0、npm 11.12.1、Python 3.12.3、Git 2.43.0です。Node.jsはnvmで導入済みであることを前提にしています。Pythonのvenvも利用できる状態が必要です。

既存の作業場所：

```bash
cd /home/taiyakinaka/salt2-practice
source ~/.nvm/nvm.sh
nvm use
bash scripts/setup.sh
```

別の環境ではリポジトリをcloneし、そのルートで同じセットアップを実行します。セットアップは専用のPython仮想環境と依存関係を作成し、画面をビルドします。`.env` がなければテンプレートから作成し、既存の設定は上書きしません。

`.env` の次の4項目を設定します。

```dotenv
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
ADMIN_EMAIL=
ADMIN_PASSWORD=
```

- `ANTHROPIC_API_KEY`：提供されたキー全体を `=` の右側に記入します。
- `ANTHROPIC_MODEL`：提供アカウントで利用可能な画像対応モデルのIDです。下記コマンドでも確認できます。
- `ADMIN_EMAIL`：初期管理者としてログインするメールアドレスです。
- `ADMIN_PASSWORD`：自分で設定する12文字以上のパスワードです。特殊文字を含める場合はdotenv形式に従って引用符で囲んでください。

キーやパスワードの実値はGitHub・チャット・公開READMEに記載しません。フロントエンドには渡しません。初期adminは利用者が0件のときだけ作成され、以降の再起動では上書きされません。

```bash
bash scripts/run.sh
```

ブラウザーで **http://localhost:8000** を開きます。ビルド済み画面とAPIを同じFastAPIサーバーから配信します。停止は `Ctrl+C` です。`.env` を変更した場合はサーバーを再起動してください。

WindowsからWSLを起動する場合：

```powershell
wsl.exe --distribution Ubuntu
```

以降のファイル操作、パッケージ導入、起動、Git操作はWSL内で行います。他案件のコード・設定・認証情報は使用していません。

## AIの接続確認

```bash
# モデル一覧だけを取得
backend/.venv/bin/python scripts/check_ai.py

# モデル未設定なら新しいOpus系（なければSonnet系）を選び、
# 架空の名刺1枚を送って8項目を比較
backend/.venv/bin/python scripts/check_ai.py --select-model --smoke-test
```

既に指定されたモデルは上書きしません。実行には有効な提供キーが必要で、画像テストはAPI利用を伴います。結果はGit管理外の `test-inputs/synthetic-ai-result.json` に保存されます。テスト画像作成にはUbuntuのDejaVu Sansフォントを使用します。

2026-10-23の確認では、提供キーに対してHTTP 401が返りました。これは今回確認した認証エラーであり、HTTP 429のレート制限とは区別しています。残高・利用上限自体は確認できていません。提供元へキーの有効性と接続先の確認を依頼する必要があります。AIが使えない間も、元画像を選択し、8項目を手入力して保存できます。

参照：[Claudeの画像入力](https://platform.claude.com/docs/en/build-with-claude/vision)、[APIエラー](https://platform.claude.com/docs/en/api/errors)。

## 利用手順

1. 初期adminでログインします。
2. 「利用者と閲覧許可」で、メールと初期パスワードを指定して一般利用者を追加します。パスワードはアプリ外で本人へ共有します。
3. 「名刺を登録」で画像を選び、「AIで名刺を読み取る」を実行します。原画像と8項目を確認し、修正して保存します。氏名のみ必須です。
4. 一覧から氏名・会社名で検索し、詳細と元画像を確認します。
5. 管理者は利用者を選び、企業・部署・人物の対象を指定して許可を付与・解除します。

名刺を登録した本人は自分の名刺を常に閲覧できます。追加許可はOR条件なので、企業の許可を解除しても部署または人物の許可が残れば閲覧できます。管理者は全件閲覧できます。

## 確認用アカウントと権限

固定の本番用パスワードやデモ管理者は同梱していません。評価時は `.env` で初期adminを作り、画面で以下の架空アカウントを作成してください。各パスワードは評価者が12文字以上で設定します。

| アカウント例 | role | 確認内容 |
| --- | --- | --- |
| 自分で指定したADMIN_EMAIL | admin | 全名刺、利用者追加、許可の変更 |
| member-a@example.test | user | 自分の登録分、付与された企業・部署・人物 |
| member-b@example.test | user | 許可のない名刺へのアクセス拒否 |

AとBがそれぞれ別企業の名刺を登録します。両企業に同名部署を作り、同姓同名の名刺も別人物として登録すると、名前だけで許可が混ざらないことを確認できます。Aへの許可を追加・解除し、一覧・検索・詳細・元画像で結果を確認してください。

自動テストは専用の一時DBに架空アカウントと画像を作り、通常のDBを書き換えません。ブラウザー検証も別のDBで実施しました。確認用パスワードを実運用に流用しないでください。

## 設計上の重要点

- **権限はAPI側で判定します。** `backend/app/main.py` の `visible_cards` が「admin・登録者・企業・部署・人物」のOR条件を作り、一覧・検索・詳細・元画像・人物候補で共用します。権限のないIDは存在しないIDと同じ404を返します。
- **表示名と識別IDを分けます。** 会社名は前後空白を除いた完全一致を同一企業とする仮定です。部署は企業ごとに別ID、人物は新規IDが初期値です。同姓同名を自動統合しません。同じ人物の別名刺だけ、閲覧可能な候補から明示的に紐付けます。
- **AI結果をそのまま確定しません。** 8項目の形式を検証し、未記載項目は空文字にします。ユーザーが確認した内容だけを保存します。画像内の指示文は抽出の指示として扱いません。
- **保存と画像は一体です。** 元画像・確定情報・登録者を同じDBトランザクションで保存します。登録者はログイン情報から設定し、入力による偽装を拒否します。再送は利用者ごとのrequest_idで重複を防ぎます。
- **認証情報をブラウザーへ公開しません。** セッションCookieはHttpOnly、DBにはトークンのハッシュを保持します。更新系にはOriginとCSRFトークンの検査を行います。画像も認証付きAPIで取得し、キャッシュを抑止します。


## APIキーを使わない部分の改善

- 期限切れでは再ログインを表示し、同じ利用者なら画像・入力・人物の紐付けを保持して再開します。別利用者への切り替えと明示的なログアウトでは破棄します。
- 画像を差し替える際は「別の名刺としてクリア」「同じ名刺の撮り直しとして保持」「キャンセル」を選択します。
- 保存後も同じ画像ファイルを再選択できます。
- 権限一覧の取得失敗は「許可なし」と区別し、再試行を表示します。
- 実起動だけが `.env` と通常DBを初期化するよう、`app.asgi` とアプリ生成関数を分離しました。

## テストと開発

```bash
bash scripts/test.sh
```

個別に実行する場合：

```bash
cd backend
.venv/bin/python -m pytest -q
cd ..
source ~/.nvm/nvm.sh
nvm use
npm --prefix frontend test
npm --prefix frontend run build
```

開発時は別々のWSLターミナルで起動できます。

```bash
# API
backend/.venv/bin/python -m uvicorn app.asgi:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

```bash
# 画面
source ~/.nvm/nvm.sh
nvm use
npm --prefix frontend run dev
```

Viteの http://localhost:5173 から `/api` をバックエンドへ転送します。

## 保存先と設定

| 設定 | 初期値・用途 |
| --- | --- |
| DATABASE_PATH | `./data/app.sqlite3`。相対パスはリポジトリルート基準 |
| SESSION_TTL_SECONDS | `28800`。セッション有効期間8時間 |
| AI_EXTRACT_TIMEOUT_SECONDS | `30`。AI接続の制限時間 |
| COOKIE_SECURE | ローカルHTTPではfalse。HTTPS環境ではtrue |
| ALLOWED_ORIGINS | localhost / 127.0.0.1の8000・5173番。必要時だけカンマ区切りで変更 |

`data/`、`test-inputs/`、`artifacts/`、`.env`、DB・付随ファイル・ログはGit管理外です。元画像、実名刺の期待値、課題PDFを公開リポジトリに入れません。

## AIツールの利用と確認

Codexを仕様整理、実装、テスト作成、コード確認、ブラウザー操作確認、README作成に使用しました。ユーザーの指定によりsubagentでバックエンド・画面・テストを分担し、バックエンドはGPT-6 Astra、画面とテストはGPT-6.1 Solを使用しました。

判断した点は、同名による権限混同を避けるID設計、元画像まで共通化した権限制御、入力内容を保持する再試行、AIモックと実API確認の分離です。生成結果は78件のテスト、型チェック・ビルド、実ブラウザーで確認しました。AIの実抽出精度は未確認として明示しています。

## 制約と提出

対象は1組織・PCブラウザー・ローカル実行です。本番運用、モバイル最適化、SSO、自己登録、招待メール、パスワード再設定、画像の一括処理、登録後の名刺編集・削除は対象外です。ログイン試行のレート制限や本番監視・バックアップ運用は未実装です。

氏名・会社名は部分一致検索です。企業名の表記揺れは自動統合しません。同じ正式名称は同一企業と扱うため、別企業が同じ正式名称を持つケースには対応していません。権限解除後のAPIは拒否しますが、既にダウンロードされた画像を回収する機能はありません。

提供キーの認証問題が解消するまで、モデル選定・実画像の抽出・期待値比較は完了しません。提供名刺と期待値も本リポジトリには未配置です。

提出物はPublic GitHub RepositoryのURLです。必要な初期アカウント・APIキー等は評価者へ非公開の方法で共有します。
