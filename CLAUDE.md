# CLAUDE.md

このファイルは、このリポジトリでコードを扱う際の Claude Code (claude.ai/code) 向けのガイドラインです。

## ビルド/実行/テスト コマンド

### 環境セットアップ
- 依存関係のインストール: `pip install -r requirements.txt`
- 仮想環境の作成: `uv venv` または `python -m venv .venv`
- 環境のアクティベート: `source .venv/bin/activate`

### カメラ & S3 アップロード (MFA必須)
- カメラ実行とS3アップロード: `python camera/camera_to_s3_mfa.py`
- 初回実行時はMFAコード（認証アプリの6桁）の入力が必要
- 2回目以降（12時間以内）はキャッシュされた認証情報を自動使用
- 停止: `Ctrl+C`

### Lambda デプロイ & テスト
- **デプロイ手順**: `deploy_lambda.md` を参照してください。
    - 依存ライブラリ（`openai` 等）を含めた zip 作成手順
    - AWS CLI を使ったデプロイコマンド
- **テストイベント**: `aws_test_event.json` を使用してください。
    - S3 イベントの JSON テンプレート
    - バケット名とオブジェクトキーを環境に合わせて書き換えて使用

### Lambda バリデーションテスト (ローカル)
- ローカルテスト実行: `python lambda/test_local.py`
- テスト内容: 正常系（ラベルなしペットボトル）、異常系（ラベルあり、禁止物）、ゴミ箱満杯検知

## システムアーキテクチャ

Wackathon 2025 向けの「感情を持ったゴミ箱システム」です。OpenAI API を活用して高度な判断を行います。

### ハイレベル・アーキテクチャフロー
1. **PCカメラ** → 定期的（5秒間隔）に画像をキャプチャ
2. **MFA認証** → AWS STS で12時間有効な一時クレデンシャルを取得
3. **AWS S3** → 画像をアップロード、S3イベントで Lambda をトリガー
4. **OpenAI API (GPT-4o-mini)** → 画像解析（分別判定、ラベル有無、満杯検知）
5. **Lambda関数** → 解析結果に基づき応答を生成
6. **OpenAI API (GPT-4o-mini-tts)** → 音声データを生成し S3 に保存
7. **スピーカー** → 生成された音声を再生

### 重要な実装詳細

**MFA認証フロー (Organizations SCP対策)**:
- AWS Organizations SCP により S3 操作には MFA が必須
- `camera/camera_to_s3_mfa.py` で STS 一時クレデンシャルを管理・キャッシュ

**ゴミ分別・判定ロジック (OpenAI)**:
- モデル: `gpt-4o-mini` (Vision)
- 判定項目:
    - ゴミ種別（燃えるゴミ、プラスチック、缶・ビン、ペットボトル）
    - **ペットボトルのラベル有無**: ラベルがある場合は「不正」と判定（透明度やパッケージで判断）
    - **ゴミ箱の満杯検知**: 画像から溢れそうな状態を検知
    - **禁止物**: 電池、ライター、危険物などを検知

**音声生成 (OpenAI)**:
- モデル: `gpt-4o-mini-tts`
- キャラクター: 「ポイっとくん」（親しみやすい口調）
- **エラー時**: システムエラー発生時は音声生成をスキップ

### 主要コンポーネント

**camera/** - 画像キャプチャと S3 アップロード
- `camera_to_s3_mfa.py`: MFA認証、キャッシュ、S3アップロードを行うメインスクリプト
- `config.py`: 設定ファイル

**lambda/** - 分別判定と音声生成ロジック
- `waste_validator.py`: メインの Lambda ハンドラー
- `openai_utils.py`: OpenAI API (Vision/TTS) との連携ロジックとプロンプト定義
- `test_local.py`: ローカルテストランナー
- `deploy_lambda.md`: デプロイ手順書
- `aws_test_event.json`: テスト用イベントテンプレート

**obniz/** - ハードウェア連携
- `index.html`: HC-SR04 超音波センサー連携

### 設定管理

**AWS設定** (`.env`):
- `AWS_REGION`, `S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MFA_SERIAL_NUMBER`

**OpenAI設定** (Lambda環境変数):
- `OPENAI_API_KEY`: OpenAI API キー (**必須**)
- `VOICE_BUCKET_NAME`: 音声保存用S3バケット名

### コードスタイル
- 言語: **日本語** (コメント、ドキュメント含む)
- 型ヒント: `Final`, `Optional`, `list[Type]` 等を使用
- フォーマッタ: Black / isort 推奨
