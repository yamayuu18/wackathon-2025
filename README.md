# Wackathon 2025 - 感情を持ったゴミ箱システム「ポイっとくん」

PCカメラでゴミを認識し、OpenAI API (GPT-4o-mini) を活用して分別判定や音声フィードバックを行うスマートゴミ箱システムです。

## 主な機能

- **画像認識**: カメラで撮影した画像を解析し、ゴミの種類（燃えるゴミ、プラスチック、缶・ビン、ペットボトル）を判定。
- **高度な判定**:
    - **ペットボトルのラベル剥離**: ラベルが剥がされていない場合、剥がすよう促します。
    - **ゴミ箱満杯検知**: ゴミ箱が溢れそうな場合、回収を依頼します。
    - **禁止物検知**: 電池やライターなどの危険物を検知し、警告します。
- **リアルタイムダッシュボード**:
    - **可視化**: 合格率、NG理由ランキング、日別推移をグラフで表示。
    - **ライブログ**: 判定結果をリアルタイムにタイムライン表示。
    - **ビジュアルエフェクト**: 判定結果に応じて画面が緑(OK)/赤(NG)にフラッシュし、デモ効果を高めます。
- **音声フィードバック**: 親しみやすいキャラクター「ポイっとくん」が、状況に合わせて音声で話しかけます（OpenAI TTS 利用）。
- **無言モード**: 画像に変化がない場合や手ブレのみの場合は、AIが空気を読んで沈黙します。
- **デモ用制御**:
    - **接続/検知分離**: 「接続開始」と「検知開始」を分け、デモのタイミングを制御可能。
    - **カウントダウン**: 検知開始時にカウントダウンを表示。
- **AR連携**: 判定結果や変化検知フラグ (`has_change`) をDBに記録し、ARアプリと連携可能です。

## システムアーキテクチャ (Webアプリ版)

1.  **iPhone (Safari)**: カメラ映像と音声をリアルタイムに取得。フラッシュや0.5倍ズームを制御。
2.  **ngrok**: 外部からのHTTPSアクセスをローカルサーバーにトンネリング。
3.  **ローカルサーバー (Mac)**:
    - **FastAPI**: WebSocketリレーサーバー & ダッシュボード配信。
    - **OpenAI Realtime API**: 画像・音声を解析し、音声応答を生成 (`gpt-4o-mini`)。
    - **AWS DynamoDB**: 判定結果と拒否理由をクラウドに記録。
4.  **厳格な判定ロジック**:
    - **OK**: 綺麗に洗ってラベル・キャップを外したペットボトル。
    - **NG**: それ以外（キャップ付き、ラベル付き、中身あり、缶・ビンなど）。

## プロジェクト構成

```
Wackathon/2025/
├── camera/
│   ├── webapp/                 # Webアプリ版 (Current)
│   │   ├── server.py           # FastAPIサーバー
│   │   ├── index.html          # フロントエンド (カメラ/マイク)
│   │   └── dashboard.html      # ダッシュボード (分析画面)
│   ├── realtime_app.py         # Realtime API クライアント (CLI版)
│   ├── database.py             # DB操作 (DynamoDB)
│   └── captured_images/        # 画像保存先
├── legacy/                     # 旧アーキテクチャ (S3/Lambda)
│   ├── camera/                 # 旧カメラ・Voicevoxスクリプト
│   └── lambda/                 # 旧Lambda関数
├── doc/
│   └── system_architecture.md  # システム構成図
├── requirements.txt            # 依存ライブラリ
├── CLAUDE.md                   # 開発ガイドライン
├── AGENTS.md                   # AIエージェント協働ガイドライン
└── README.md                   # このファイル
```

## セットアップと実行 (Webアプリ版)

### 1. 環境構築

```bash
pip install -r requirements.txt
```

### 2. 環境変数 (.env)

プロジェクトルートに `.env` を作成:

```ini
OPENAI_API_KEY=sk-...
REALTIME_MODEL=gpt-4o-mini-realtime-preview
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-northeast-1
DYNAMODB_TABLE_NAME=waste_disposal_history
# デモ調整用
IMAGE_INTERVAL=10       # 画像送信間隔(秒)
DETECTION_DELAY=5       # 検知開始までの待機時間(秒)
VAD_THRESHOLD=0.9       # 音声検知感度(0.0-1.0)
USE_MAC_SPEAKER=true    # Macのスピーカーを使用するか
```

### 3. サーバー起動

```bash
python camera/webapp/server.py
```

### 4. ngrok起動

別のターミナルで実行:

```bash
ngrok http 8000
```

### 5. アクセス

- **スマホ (カメラ)**: ngrokのURL (https://...) を開く
- **PC (ダッシュボード)**: `http://localhost:8000/dashboard` を開く

## 旧アーキテクチャ (S3/Lambda)
以前の「カメラ撮影 -> S3 -> Lambda -> Voicevox」構成は `legacy/` フォルダに移動されました。詳細は `legacy/camera/` や `legacy/lambda/` 内のファイルを参照してください。

## 開発ガイドライン
詳細なルールは [CLAUDE.md](CLAUDE.md) を参照してください。
