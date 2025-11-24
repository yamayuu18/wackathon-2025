# CLAUDE.md

このファイルは、このリポジトリでコードを扱う際の Claude Code (claude.ai/code) 向けのガイドラインです。

## ビルド/実行/テスト コマンド

### 環境セットアップ
- 依存関係のインストール: `pip install -r requirements.txt`
- 仮想環境の作成: `uv venv` または `python -m venv .venv`
- 環境のアクティベート: `source .venv/bin/activate`

### ローカル実行 (Mac)
1. **Webサーバー & 音声再生 (Voicevox)**:
   - 実行: `python camera/app.py`
   - 役割: S3の解析結果を監視し、Voicevoxで音声を生成してMacで再生
   - **注意**: 起動したらそのまま放置（停止しない）

2. **カメラ & S3 アップロード (MFA必須)**:
   - 実行: `python camera/camera_to_s3_mfa.py`
   - 役割: 10秒ごとに画像を撮影してS3へアップロード
   - **注意**: `app.py` とは別のターミナルで実行すること

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
1. **PCカメラ (iPhone連係)** → 定期的（10秒間隔）に画像をキャプチャ (`camera_to_s3_mfa.py`)
2. **MFA認証** → AWS STS で12時間有効な一時クレデンシャルを取得
3. **AWS S3** → 画像をアップロード、S3イベントで Lambda をトリガー
4. **OpenAI API (GPT-4o-mini)** → 画像解析（分別判定、ラベル有無、満杯検知）
5. **Lambda関数** → 解析結果をJSONとして S3 に保存 (`wackathon-2025-voice-responses/results/`)
6. **ローカルサーバー (`app.py`)** → S3をポーリングして新しい結果を検知
7. **Voicevox (Local)** → テキストから音声を生成
8. **Macスピーカー** → 生成された音声を再生 (`afplay`)

### 重要な実装詳細

**MFA認証フロー (Organizations SCP対策)**:
- AWS Organizations SCP により S3 操作には MFA が必須
- `camera/camera_to_s3_mfa.py` で STS 一時クレデンシャルを管理・キャッシュ

**ゴミ分別・判定ロジック (OpenAI)**:
- モデル: `gpt-4o-mini` (Vision)
- 判定項目:
    - ゴミ種別（燃えるゴミ、プラスチック、缶・ビン、ペットボトル）
    - **ペットボトルのラベル有無**: ラベルがある場合は「不正」と判定
    - **ゴミ箱の満杯検知**: 画像から溢れそうな状態を検知
    - **禁止物**: 電池、ライター、危険物などを検知

**音声生成 (Voicevox)**:
- エンジン: Voicevox (Local API)
- キャラクター: ずんだもん (Speaker ID: 3)
- **バックアップ**: `ENABLE_OPENAI_TTS=true` で OpenAI TTS も利用可能

**データベース (Local SQLite)**:
- ファイル: `camera/waste_data.db`
- テーブル: `disposal_history`
- 内容: タイムスタンプ、判定結果、検出アイテム、メッセージ

### 主要コンポーネント

**camera/** - ローカル実行用スクリプト
- `app.py`: S3監視、Voicevox連携、音声再生を行うサーバー
- `camera_to_s3_mfa.py`: 画像キャプチャとS3アップロード
- `voicevox_client.py`: Voicevox API クライアント
- `config.py`: 設定ファイル

**lambda/** - 分別判定ロジック
- `waste_validator.py`: メインの Lambda ハンドラー
- `openai_utils.py`: OpenAI API (Vision) との連携ロジック
- `deploy_lambda.md`: デプロイ手順書

### 設定管理

**AWS設定** (`.env`):
- `AWS_REGION`, `S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MFA_SERIAL_NUMBER`

**OpenAI設定** (Lambda環境変数):
- `OPENAI_API_KEY`: OpenAI API キー (**必須**)
- `VOICE_BUCKET_NAME`: 結果保存用S3バケット名

### コードスタイル
- 言語: **日本語** (コメント、ドキュメント含む)
- 型ヒント: `Final`, `Optional`, `list[Type]` 等を使用
- フォーマッタ: Black / isort 推奨

## ハードウェアセットアップ (ゴミ箱内部)

**iPhoneの固定方法**:
- **場所**: ゴミ箱の蓋の裏側
- **向き**: 背面カメラが下（ゴミ箱の底）を向くように設置
- **固定具**: 1/4インチネジ（カメラ用） + スマホホルダー
    - 蓋に穴を開け、ボルトとナットでホルダーを水平に固定
- **照明**: 内部が暗いため、LEDライトの追加を推奨
- **電源**: 長時間稼働のため、充電ケーブルを外部に引き出す

## 将来のアーキテクチャ構想 (Realtime API)

**OpenAI Realtime API (Multimodal)** を導入し、より自然で低遅延な対話を実現する計画です。

- **目的**:
    - **低遅延**: 画像解析と音声生成のラグを最小限に抑える
    - **漫才機能**: ユーザーのマイク入力を受け付け、双方向の会話（ボケ・ツッコミ）を実現
    - **割り込み**: ユーザーの発話に合わせてシステムが応答を中断・変更

- **構成**:
    - **入力**: iPhoneマイク（音声） + iPhoneカメラ（画像ストリーム）
    - **処理**: OpenAI Realtime API (GPT-4o) が音声と画像を直接処理
    - **出力**: 音声ストリームをMacで再生

