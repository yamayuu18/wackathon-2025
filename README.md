# Wackathon 2025 - 感情を持ったゴミ箱システム「ポイっとくん」

PCカメラでゴミを認識し、OpenAI API (GPT-4o-mini) を活用して分別判定や音声フィードバックを行うスマートゴミ箱システムです。

## 主な機能

- **画像認識**: カメラで撮影した画像を解析し、ゴミの種類（燃えるゴミ、プラスチック、缶・ビン、ペットボトル）を判定。
- **高度な判定**:
    - **ペットボトルのラベル剥離**: ラベルが剥がされていない場合、剥がすよう促します。
    - **ゴミ箱満杯検知**: ゴミ箱が溢れそうな場合、回収を依頼します。
    - **禁止物検知**: 電池やライターなどの危険物を検知し、警告します。
- **音声フィードバック**: 親しみやすいキャラクター「ポイっとくん」が、状況に合わせて音声で話しかけます（OpenAI TTS 利用）。
- **距離センサー連携**: Obniz + 超音波センサーでゴミ箱への接近を検知（Google Apps Script連携）。

## システムアーキテクチャ

1. **PCカメラ**: 5秒ごとに画像を撮影し、AWS S3 にアップロード。
2. **AWS S3**: 画像が保存されるとイベント通知を発火。
3. **AWS Lambda**: イベントを受け取り、OpenAI API を呼び出して画像を解析。
4. **OpenAI API**:
    - `gpt-4o-mini` (Vision): 画像解析・判定。
5. **ローカルサーバー (Mac)**:
    - **Voicevox**: テキストから音声を生成（ずんだもん）。
    - **SQLite DB**: ゴミ捨て履歴（日時、判定結果）をローカルに保存。
6. **スピーカー**: 生成された音声をMacで再生。

## プロジェクト構成

```
Wackathon/2025/
├── camera/
│   ├── camera_to_s3_mfa.py     # メイン: MFA認証付きS3アップロード
│   ├── config.py               # 設定ファイル
│   ├── test_cache.py           # 認証情報キャッシュテスト
│   └── captured_images/        # ローカル保存用（.gitignore）
├── lambda/
│   ├── waste_validator.py      # Lambda関数エントリーポイント
│   ├── openai_utils.py         # OpenAI API 連携ロジック
│   ├── test_local.py           # ローカルテストスクリプト
│   ├── deploy_lambda.md        # デプロイ手順書
│   └── aws_test_event.json     # テスト用イベントテンプレート
├── obniz/
│   └── index.html              # Obniz 距離センサー連携
├── doc/
│   └── poitokun_mermaid.html   # システム構成図
├── requirements.txt            # 依存ライブラリ
├── CLAUDE.md                   # 開発ガイドライン
├── AGENTS.md                   # AIエージェント協働ガイドライン
└── README.md                   # このファイル
```

## セットアップと実行

### 1. 環境構築

```bash
# 依存ライブラリのインストール
pip install -r requirements.txt
```

### 2. AWS設定 (.env)

プロジェクトルートに `.env` ファイルを作成し、以下の情報を設定してください。

```ini
AWS_REGION=ap-northeast-1
S3_BUCKET_NAME=wackathon-2025-trash-images
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
MFA_SERIAL_NUMBER=arn:aws:iam::...:mfa/...
```

### 3. カメラ・アップロードの実行

MFA認証（多要素認証）を使用してS3へアップロードします。

```bash
python camera/camera_to_s3_mfa.py
```

初回実行時は、認証アプリ（Google Authenticator等）の6桁のコード入力が求められます。認証情報は12時間キャッシュされます。

### 4. Lambda デプロイ

AWS Lambda へのデプロイ方法は [lambda/deploy_lambda.md](lambda/deploy_lambda.md) を参照してください。

## 開発ガイドライン

詳細な開発ルールやコードスタイルについては [CLAUDE.md](CLAUDE.md) を参照してください。
