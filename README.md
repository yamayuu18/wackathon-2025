# Wackathon 2025 - ポイっとくん

ペットボトル専用スマートゴミ箱システム。OpenAI Realtime API を活用し、関西弁で話す厳格な検査官キャラクター「ポイっとくん」がゴミ分別を指導します。

## 主な機能

- **厳格なペットボトル判定**: キャップ・ラベル・中身をチェック
- **音声フィードバック**: 関西弁で褒める/叱る
- **無言モード**: 変化がない場合は自律的に沈黙
- **リアルタイムダッシュボード**: 統計・ログ・フラッシュエフェクト
- **AR連携対応**: `has_change` フラグをDBに記録

## システムアーキテクチャ

```
iPhone (Safari) ──WebSocket──► ngrok ──► Mac (server.py) ──► OpenAI Realtime API
                                                         └──► AWS DynamoDB
```

## プロジェクト構成

```
Wackathon/2025/
├── camera/
│   ├── webapp/
│   │   ├── public/              # 静的ファイル
│   │   │   ├── index.html       # スマホ用UI
│   │   │   └── dashboard.html   # PC用ダッシュボード
│   │   └── server.py            # FastAPIサーバー
│   ├── database.py              # DynamoDB操作
│   ├── captured_images/         # 画像保存（自動作成）
│   └── captured_audio/          # 音声保存（自動作成）
├── legacy/                      # 旧S3/Lambda構成
├── doc/
│   ├── system_architecture.md
│   └── database_schema.md
├── .env.example
├── requirements.txt
├── CLAUDE.md                    # 開発ガイドライン
├── AGENTS.md                    # AIエージェント協働ガイド
└── README.md
```

## セットアップ

### 1. 環境構築

```bash
# 仮想環境
python -m venv .venv
source .venv/bin/activate

# 依存関係
pip install -r requirements.txt
```

### 2. 環境変数

```bash
cp .env.example .env
```

`.env` を編集:

```ini
# 必須
OPENAI_API_KEY=sk-...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-northeast-1
DYNAMODB_TABLE_NAME=waste_disposal_history

# オプション
WS_AUTH_TOKEN=your_secure_token   # 未設定時は自動生成
REALTIME_MODEL=gpt-4o-mini-realtime-preview
IMAGE_INTERVAL=3                  # 画像送信間隔(秒)
DETECTION_DELAY=5                 # 検知開始待機(秒)
VAD_THRESHOLD=0.9                 # 音声検知感度
USE_MAC_SPEAKER=true              # PCスピーカー出力
```

### 3. 起動

**ターミナル1: サーバー**
```bash
python camera/webapp/server.py
```

**ターミナル2: ngrok**
```bash
ngrok http 8000
```

### 4. アクセス

- **スマホ**: ngrok URL (`https://xxx.ngrok-free.dev`)
- **ダッシュボード**: `http://localhost:8000/dashboard`

## セキュリティ

- WebSocket認証トークン（`/config` から自動取得）
- Base64サイズ制限 (10MB)
- 静的ファイル分離 (`public/` ディレクトリ)
- 指数バックオフ再接続

## 判定ルール

| 結果 | 条件 |
|------|------|
| OK | キャップなし・ラベルなし・中身なし |
| NG | キャップあり、ラベルあり、中身あり、缶・ビン等 |

## 開発ガイドライン

- 技術詳細: [CLAUDE.md](CLAUDE.md)
- エージェント協働: [AGENTS.md](AGENTS.md)
- アーキテクチャ: [doc/system_architecture.md](doc/system_architecture.md)
