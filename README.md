# Wackathon 2025 - ポイっとくん

ペットボトル専用スマートゴミ箱システム。OpenAI Realtime API を活用し、関西弁で話す厳格な検査官キャラクター「ポイっとくん」がゴミ分別を指導します。
判定結果に応じて、**Obniz連携サーボモーター**がゴミを自動で振り分けます。

## 主な機能

- **柔軟なペットボトル判定**: キャップ・ラベルが付いていてもOKとして受け入れ
- **空っぽ判定強化**: 基準画像 (`empty_bin_reference.jpg`) と比較による誤検知防止
- **音声フィードバック**: 関西弁で褒める/叱る
- **自動分別**: Obniz + サーボモーターでOK/NGを物理的に振り分け
- **無言モード**: 変化がない場合は自律的に沈黙
- **リアルタイムダッシュボード**: 統計・ログ・フラッシュエフェクト
- **AR連携対応**: ARグラスへの音声ルーティング

## システムアーキテクチャ

```
iPhone (Safari) ──WebSocket──► ngrok ──► AWS EC2 (server.py) ──► OpenAI Realtime API
   (AR Glass)                                     ├──► AWS DynamoDB
                                                  └──► Obniz ──► Servo Motor
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
│   ├── captured_images/         # 画像保存
│   └── captured_audio/          # 音声保存
├── doc/
│   ├── AR_INTEGRATION.md        # AR連携ガイド
│   ├── DEPLOY_AWS.md            # AWSデプロイガイド
│   ├── UPDATE_PROCEDURE.md      # 更新手順書
│   └── system_architecture.md   # 詳細構成図
├── .env.example
├── requirements.txt
├── CLAUDE.md                    # 技術詳細・開発ガイド
├── AGENTS.md                    # AIエージェント協働ガイド
└── README.md
```

## セットアップ

### 1. 環境構築

```bash
### 1. 環境構築

```bash
# 1. 仮想環境 (Python)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Node.js (Obniz用)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
npm install obniz
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

# Obniz (サーボ制御)
OBNIZ_ID=3684-4196
SERVO_RESET_DELAY=3

# オプション
WS_AUTH_TOKEN=your_token          # セキュリティ用トークン
AUDIO_ENDPOINT=camera             # camera または ar
REALTIME_MODEL=gpt-4o-mini-realtime-preview
IMAGE_INTERVAL=15                 # 画像送信間隔(秒)
DETECTION_DELAY=5                 # 検知開始待機(秒)
USE_MAC_SPEAKER=false             # サーバー側で音を鳴らすか (AWSではfalse)
```

### 3. 起動

**AWS (tmux使用)**
```bash
tmux
python3 camera/webapp/server.py
```
*(ngrokは別途サービスまたはtmux別ウィンドウで起動)*

### 4. アクセス

- **スマホ**: ngrok URL (`https://xxx.ngrok-free.dev`)
- **ダッシュボード**: `/dashboard`
- **AR用音声**: WebSocket接続時に特定トークンを使用

## デプロイ & 更新

- **AWS構築**: [doc/DEPLOY_AWS.md](doc/DEPLOY_AWS.md)
- **コード更新**: [doc/UPDATE_PROCEDURE.md](doc/UPDATE_PROCEDURE.md)

## 判定ルール

| 結果 | 条件 | サーボ動作 |
|------|------|------------|
| OK | ペットボトル (キャップ・ラベルありでもOK) | 45度 (中へ) |
| NG | ペットボトル以外 (缶・ビン・燃えるゴミなど) | 135度 (外へ) |
| 静観 | 空のゴミ箱 (変化なし) | 動作なし (90度維持) |
| 待機 | - | 90度 |

## 開発ガイドライン

- 技術詳細: [CLAUDE.md](CLAUDE.md)
- エージェント協働: [AGENTS.md](AGENTS.md)
