# CLAUDE.md

このファイルは、このリポジトリでコードを扱う際の Claude Code (claude.ai/code) 向けのガイドラインです。

## ビルド/実行/テスト コマンド

### 環境セットアップ
```bash
# 仮想環境の作成
uv venv
# または
python -m venv .venv

# 環境のアクティベート
source .venv/bin/activate

# 依存関係のインストール
pip install -r requirements.txt
```

### ローカル実行 (Webアプリ版)
```bash
# 1. サーバー起動
python camera/webapp/server.py

# 2. ngrok起動（別ターミナル）
ngrok http 8000

# 3. iPhoneからngrokのURLにアクセス
```

### Legacy (S3/Lambda)
- `legacy/` フォルダに移動済み
- 詳細: `legacy/lambda/deploy_lambda.md`

## システムアーキテクチャ

### データフロー
```
iPhone (Safari) → ngrok → Mac (server.py) → OpenAI Realtime API
                                         → AWS DynamoDB
```

### 主要コンポーネント

| コンポーネント | ファイル | 役割 |
|--------------|---------|------|
| バックエンド | `camera/webapp/server.py` | FastAPI + WebSocketリレー |
| フロントエンド | `camera/webapp/public/index.html` | カメラ/マイク制御 |
| ダッシュボード | `camera/webapp/public/dashboard.html` | 統計表示 |
| DB操作 | `camera/database.py` | DynamoDB CRUD |

### ディレクトリ構成
```
camera/webapp/
├── public/              # 静的ファイル（セキュリティのため分離）
│   ├── index.html       # スマホ用UI
│   └── dashboard.html   # PC用ダッシュボード
└── server.py            # バックエンド
```

## セキュリティ機能

### WebSocket認証
- トークンベース認証（`WS_AUTH_TOKEN`）
- 未設定時は起動時に自動生成（ログに出力）

### 入力検証
- Base64サイズ制限: 10MB
- パストラバーサル防止: `sanitize_item_id()`
- JSONパースエラーハンドリング

### 並行処理安全
- `SpeakingState` クラスによるAI発話状態管理
- `session_state_lock` による状態アクセス保護
- Function Call冪等性チェック

### 再接続
- 指数バックオフ（1秒〜60秒、最大10回）

## 環境変数 (.env)

```bash
# 必須
OPENAI_API_KEY=sk-...

# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-northeast-1
DYNAMODB_TABLE_NAME=waste_disposal_history

# オプション
WS_AUTH_TOKEN=your_secure_token    # 未設定時は自動生成
REALTIME_MODEL=gpt-4o-mini-realtime-preview
REALTIME_VOICE=verse
AUDIO_ENDPOINT=camera              # camera または ar

# デモ調整
IMAGE_INTERVAL=3                   # 画像送信間隔(秒)
DETECTION_DELAY=5                  # 検知開始待機(秒)
VAD_THRESHOLD=0.9                  # 音声検知感度
USE_MAC_SPEAKER=true               # PCスピーカー出力
```

## 判定ロジック

### 二段階変化検知
1. **OpenCV差分チェック**: 閾値30以下 → APIスキップ
2. **AI判断**: 手ブレのみ → `has_change=False` → 沈黙

### ペットボトル判定
- **OK**: キャップなし・ラベルなし・中身なし
- **NG**: 上記以外（缶、ビン、燃えるゴミ含む）

### 半二重通話
- AI発話中はマイク入力をミュート
- エコー/無限ループ防止

## コードスタイル

- **Python**: PEP 8 + 型ヒント
- **Docstring**: Google style
- **命名**: snake_case (変数/関数), PascalCase (クラス), UPPER_CASE (定数)
- **ログ**: `logging` モジュール使用、`exc_info=True` で詳細出力

## APIエンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/` | index.html |
| GET | `/config` | 設定値 + WebSocketトークン |
| GET | `/dashboard` | ダッシュボード |
| GET | `/api/stats` | 統計JSON |
| WS | `/ws?role=camera&token=xxx` | WebSocket接続 |

## ハードウェア

- **iPhone**: ゴミ箱蓋裏に設置（背面カメラ使用）
- **照明**: LEDライト推奨（フラッシュも可）
