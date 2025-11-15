# Wackathon 2025 - ゴミ箱発話システム

PCのカメラから画像を取得し、AWS S3にアップロードするシステムです。

## プロジェクト構成

```
Wackathon/2025/
├── camera/
│   ├── camera_capture.py      # カメラ撮影プログラム（ローカル保存版）
│   ├── camera_to_s3.py         # AWS S3アップロード版（未実装）
│   ├── config.py               # 設定ファイル
│   └── captured_images/        # ローカル保存用ディレクトリ
├── obniz/
│   └── index.html              # obniz距離センサー連携
├── doc/
│   └── poitokun_mermaid.html   # システム構成図
├── requirements.txt            # Pythonライブラリ依存関係
└── README.md                   # このファイル
```

## セットアップ

### 1. 必要なライブラリのインストール

```bash
pip install -r requirements.txt
```

### 2. カメラ撮影プログラムの実行

```bash
cd camera
python camera_capture.py
```

プログラムが起動すると、5秒ごとにカメラから画像を取得し、`camera/captured_images/` に保存します。

### 3. 終了方法

`Ctrl+C` でプログラムを停止できます。

## 設定のカスタマイズ

[camera/config.py](camera/config.py) で以下の設定を変更できます：

- `CAPTURE_INTERVAL_SECONDS`: 撮影間隔（デフォルト: 5秒）
- `CAMERA_DEVICE_ID`: カメラデバイスID（デフォルト: 0）
- `IMAGE_WIDTH`, `IMAGE_HEIGHT`: 画像解像度（デフォルト: 1280x720）
- `IMAGE_QUALITY`: JPEG品質（1-100、デフォルト: 95）

## AWS S3連携（今後実装予定）

AWS環境が提供され次第、以下の機能を実装します：

1. `camera_to_s3.py`: 撮影した画像を自動的にS3バケットにアップロード
2. AWS認証情報の設定（環境変数または`.env`ファイル）
3. S3バケット名とリージョンの設定

## システム構成

システム全体の構成図は [doc/poitokun_mermaid.html](doc/poitokun_mermaid.html) を参照してください。

## トラブルシューティング

### カメラが開けない場合

- カメラが他のアプリケーションで使用中でないか確認
- `config.py` の `CAMERA_DEVICE_ID` を変更してみる（0 → 1）
- カメラのアクセス許可が必要な場合があります（macOSの場合、システム環境設定 > セキュリティとプライバシー > カメラ）

### 画像が保存されない場合

- `camera/captured_images/` ディレクトリの書き込み権限を確認
- ディスク容量を確認

## ライセンス

Wackathon 2025 プロジェクト用
