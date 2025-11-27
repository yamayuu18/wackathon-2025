# CLAUDE.md

このファイルは、このリポジトリでコードを扱う際の Claude Code (claude.ai/code) 向けのガイドラインです。

## ビルド/実行/テスト コマンド

### 環境セットアップ
- 依存関係のインストール: `pip install -r requirements.txt`
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

**ゴミ分別・判定ロジック (OpenAI)**:
- モデル: `gpt-4o-mini` (Realtime API)
- **厳格なペットボトル判定**:
    - キャップ・ラベル・中身がある場合はNG
    - 缶・ビン・燃えるゴミはNG

**データベース (AWS DynamoDB)**:
- サービス: AWS DynamoDB
- テーブル名: `waste_disposal_history` (環境変数で指定可)
- 構成: Partition Key=`user_id`, Sort Key=`timestamp`

### 主要コンポーネント

**camera/webapp/** - Webアプリ版
- `server.py`: バックエンド (FastAPI)
- `index.html`: フロントエンド (Camera/Audio)

**camera/** - 共通
- `database.py`: DB操作
- `realtime_app.py`: Realtime API クライアント (CLI版)

**legacy/** - 旧アーキテクチャ
- `camera/`: 旧カメラ・Voicevoxスクリプト
- `lambda/`: 旧Lambda関数

### 設定管理
- `.env`: `OPENAI_API_KEY`, `REALTIME_MODEL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `DYNAMODB_TABLE_NAME`

## ハードウェアセットアップ (ゴミ箱内部)
- **iPhone**: ゴミ箱の蓋の裏側に設置（背面カメラ使用）
- **照明**: LEDライト推奨（フラッシュも利用可能）

