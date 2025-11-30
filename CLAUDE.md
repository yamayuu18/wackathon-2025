# CLAUDE.md

このファイルは、このリポジトリでコードを扱う際の Claude Code (claude.ai/code) 向けのガイドラインです。

## ビルド/実行/テスト コマンド

### 環境セットアップ
- 依存関係のインストール: `pip install -r requirements.txt` (または `pip install opencv-python numpy ...`)
- 仮想環境の作成: `uv venv` または `python -m venv .venv`
- 環境のアクティベート: `source .venv/bin/activate`

### ローカル実行 (Webアプリ版 - Current)
1. **サーバー起動**:
   - 実行: `python camera/webapp/server.py`
   - 役割: FastAPIサーバー起動、OpenAI Realtime API 接続
2. **ngrok起動**:
   - 実行: `ngrok http 8000`
   - 役割: 外部公開 (HTTPS)
3. **iPhoneアクセス**:
   - ngrokのURLを開く

### ローカル実行 (Legacy S3/Lambda)
1. **Webサーバー & 音声再生**: `python legacy/camera/app.py`
2. **カメラ & S3 アップロード**: `python legacy/camera/camera_to_s3_mfa.py`

### Lambda デプロイ & テスト
- **デプロイ手順**: `legacy/lambda/deploy_lambda.md` を参照してください。

## システムアーキテクチャ (Webアプリ版)

### ハイレベル・アーキテクチャフロー
1. **iPhone (Safari)** → カメラ映像・音声をWebSocketで送信
2. **ngrok** → HTTPSトンネリング
3. **Mac (server.py)** → 画像保存、OpenAIへのリレー
4. **OpenAI Realtime API** → 画像解析・音声生成 (`gpt-4o-mini`)
5. **Mac (server.py)** → 音声データ受信、ブラウザへ転送
6. **iPhone (Safari)** → 音声再生

### 重要な実装詳細

### 重要な実装詳細

**変化検知と無言モード**:
- **OpenCV差分チェック**: 画像に変化がない場合、APIへの送信をスキップします。
- **AI変化判定**: 手ブレ等で送信された場合でも、AIが「意味のある変化なし」と判断すれば `has_change=False` を記録し、**発話しません**。

**ゴミ分別・判定ロジック (OpenAI)**:
- モデル: `gpt-4o-mini` (Realtime API)
- **厳格なペットボトル判定**:
    - キャップ・ラベル・中身がある場合はNG
    - 缶・ビン・燃えるゴミはNG
- **半二重通話 (Half-Duplex)**:
    - AI発話中はマイク入力をサーバー側でミュートし、エコーや無限ループを防止 (`is_ai_speaking` フラグ)。

**データベース (AWS DynamoDB)**:
- サービス: AWS DynamoDB
- テーブル名: `waste_disposal_history` (環境変数で指定可)
- 構成: Partition Key=`user_id`, Sort Key=`timestamp`
- **スキーマ詳細**: `doc/database_schema.md` を参照

**ダッシュボード**:
- エンドポイント: `/dashboard` (HTML), `/api/stats` (JSON)
- 機能: リアルタイム集計、日別推移、NG理由分析、フラッシュエフェクト

### 主要コンポーネント

**camera/webapp/** - Webアプリ版
- `server.py`: バックエンド (FastAPI, WebSocket, API)
- `index.html`: スマホ用フロントエンド (Camera/Audio)
- `dashboard.html`: PC用ダッシュボード (Chart.js)

**camera/** - 共通
- `database.py`: DB操作
- `realtime_app.py`: Realtime API クライアント (CLI版)

**legacy/** - 旧アーキテクチャ
- `camera/`: 旧カメラ・Voicevoxスクリプト
- `lambda/`: 旧Lambda関数

### 設定管理
- `.env`:
    - APIキー: `OPENAI_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
    - 設定: `REALTIME_MODEL`, `AWS_DEFAULT_REGION`, `DYNAMODB_TABLE_NAME`
    - デモ調整: `IMAGE_INTERVAL`, `DETECTION_DELAY`, `VAD_THRESHOLD`, `USE_MAC_SPEAKER`

## ハードウェアセットアップ (ゴミ箱内部)
- **iPhone**: ゴミ箱の蓋の裏側に設置（背面カメラ使用）
- **照明**: LEDライト推奨（フラッシュも利用可能）

