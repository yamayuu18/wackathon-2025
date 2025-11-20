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

### 認証情報キャッシュ管理
- テストキャッシュ作成: `python camera/test_cache.py create`
- キャッシュ状態確認: `python camera/test_cache.py check`
- 期限切れキャッシュ作成: `python camera/test_cache.py expired`
- キャッシュ削除: `python camera/test_cache.py delete`

### Lambda バリデーションテスト
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
    - **ペットボトルのラベル有無**: ラベルがある場合は「不正」と判定
    - **ゴミ箱の満杯検知**: 画像から溢れそうな状態を検知
    - **禁止物**: 電池、ライター、危険物などを検知

**音声生成 (OpenAI)**:
- モデル: `gpt-4o-mini-tts` (または `tts-1`)
- キャラクター: 「ポイとくん」（親しみやすい口調）

### 主要コンポーネント

**camera/** - 画像キャプチャと S3 アップロード
- `config.py`: 環境変数対応の設定ファイル
- `camera_to_s3_mfa.py`: MFA認証、キャッシュ、S3アップロードを行うメインスクリプト
- `test_cache.py`: 認証情報キャッシュのテストユーティリティ
- `captured_images/`: ローカル保存ディレクトリ (gitignored)

**lambda/** - 分別判定と音声生成ロジック
- `waste_validator.py`: メインの Lambda ハンドラー
- `openai_utils.py`: OpenAI API (Vision/TTS) との連携ロジックとプロンプト定義
- `test_local.py`: OpenAI API をモックしたローカルテストランナー
- `polly_config.py`: (旧) Polly設定。※OpenAI移行に伴い、S3バケット名などの定数のみ利用中

**obniz/** - ハードウェア連携
- `index.html`: HC-SR04 超音波センサー連携、GAS へのデータ送信

**doc/** - ドキュメント
- `poitokun_mermaid.html`: システムフロー図

### 設定管理

**カメラ設定** (`camera/config.py`):
- `CAMERA_DEVICE_ID`, `IMAGE_WIDTH`, `IMAGE_HEIGHT`, `CAPTURE_INTERVAL_SECONDS` 等

**AWS設定** (`.env`):
- `AWS_REGION`, `S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MFA_SERIAL_NUMBER`

**OpenAI設定** (Lambda環境変数):
- `OPENAI_API_KEY`: OpenAI API キー (**必須**)

### AWS 統合状況

**完了**:
- MFA付き S3 アップロード
- Lambda ロジック (OpenAI 対応版) のローカル実装・テスト
- クレデンシャルキャッシュシステム

**AWS デプロイ待ち**:
- Lambda 関数の AWS へのデプロイ（`openai` ライブラリを含むレイヤーまたはパッケージが必要）
- Lambda 環境変数 `OPENAI_API_KEY` の設定
- S3 イベントトリガーの設定

## OpenAI API 統合

### 移行の背景
AWS Rekognition では困難だった「ペットボトルのラベル剥がし忘れ」の判定や、「ゴミ箱の満杯検知」を実現するため、GPT-4o-mini に移行しました。

### レスポンス形式
Lambda は以下の形式で JSON を返します：

```json
{
  "statusCode": 200,
  "body": {
    "is_valid": true,
    "message": "ありがとうございます！...",
    "audio_url": "https://...",
    "detected_items": ["Plastic Bottle"],
    "categories": ["ペットボトル"],
    "prohibited_items": [],
    "label_removed": true,
    "is_full": false
  }
}
```

### コードスタイル
- 型ヒント: `Final`, `Optional`, `list[Type]` 等を使用
- インポート順序: 標準ライブラリ → サードパーティ → ローカル
- Docstrings: Google スタイル
- 言語: **日本語** (コメント、ドキュメント含む)
