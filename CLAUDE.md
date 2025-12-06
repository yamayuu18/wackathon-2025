# CLAUDE.md

このファイルは、このリポジトリでコードを扱う際の Claude Code (claude.ai/code) 向けのガイドラインです。

## ビルド/実行/テスト コマンド

### 環境セットアップ
```bash
# 仮想環境の作成
python3 -m venv .venv
source .venv/bin/activate

# 依存関係のインストール
pip install -r requirements.txt
```

### AWS EC2 実行 (本番)
```bash
# tmux を使用してセッション維持
tmux
python3 camera/webapp/server.py

# ngrok起動（別ウィンドウ）
ngrok http 8000
```

### デプロイ & 更新
- **初回構築**: `doc/DEPLOY_AWS.md` 参照
- **コード更新**: `doc/UPDATE_PROCEDURE.md` 参照 (Pull -> Restart)

## システムアーキテクチャ

### データフロー
```
iPhone (Safari) → ngrok → AWS EC2 (server.py) → OpenAI Realtime API
                                             ├──→ AWS DynamoDB
                                             └──→ Obniz (Servo)
```

### 主要コンポーネント

| コンポーネント | ファイル | 役割 |
|--------------|---------|------|
| バックエンド | `camera/webapp/server.py` | FastAPI + WebSocketリレー + Obniz制御 |
| フロントエンド | `camera/webapp/public/index.html` | カメラ/マイク制御 |
| ダッシュボード | `camera/webapp/public/dashboard.html` | 統計・ログ・画像確認 |
| DB操作 | `camera/database.py` | DynamoDB CRUD |
| Obniz連携 | `server.py` (RelayHub) | サーボモーター制御 (0°/90°/180°) |

## セキュリティ機能

### WebSocket認証
- トークンベース認証（`WS_AUTH_TOKEN`）
- ARクライアントもトークンを使用

### 入力検証
- Base64サイズ制限: 10MB
- パストラバーサル防止: `sanitize_item_id()`

### 並行処理安全
- `SpeakingState` クラスによるAI発話状態管理
- `session_state_lock` による状態アクセス保護
- `asyncio.Lock` による Obniz 制御排他

## 環境変数 (.env)

```bash
# 必須
OPENAI_API_KEY=sk-...

# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-northeast-1
DYNAMODB_TABLE_NAME=waste_disposal_history
OBNIZ_ID=3684-4196
SERVO_RESET_DELAY=3

# オプション
WS_AUTH_TOKEN=your_secure_token
REALTIME_MODEL=gpt-4o-mini-realtime-preview
AUDIO_ENDPOINT=camera              # camera または ar
IMAGE_INTERVAL=15                  # 画像送信間隔(秒)
USE_MAC_SPEAKER=false              # サーバー側音声出力
```

## 判定ロジック

### 二段階変化検知
1. **OpenCV差分チェック**: 閾値30以下 → APIスキップ
2. **AI判断**: `has_change=False` → 沈黙

### エージェント振る舞い
- **画像あり**: 即座に `log_disposal` 呼び出し → サーボ制御 → 音声フィードバック
- **画像なし**: 雑談応答 (会話モード)

### サーボ制御 (Obniz)
- **OK**: 0度 (Allow)
- **NG**: 180度 (Reject)
- **Default**: 90度 (Wait)

## コードスタイル

- **Python**: PEP 8 + 型ヒント + `obniz` ライブラリ
- **Logging**: `logging` モジュール使用、`exc_info=True`
- **非同期**: `asyncio` を全面的に採用

## APIエンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/` | index.html |
| GET | `/config` | 設定値 + WebSocketトークン |
| GET | `/dashboard` | ダッシュボード |
| GET | `/api/stats` | 統計JSON |
| GET | `/api/latest-image` | 最新判定画像 |
| WS | `/ws?role=camera&token=...` | WebSocket接続 |
