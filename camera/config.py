"""カメラ撮影プログラムの設定ファイル

このモジュールは、カメラ撮影とAWS S3アップロードに関する設定を管理します。
"""

from typing import Final

from pathlib import Path

# カメラ設定
CAMERA_DEVICE_ID: Final[int] = 1  # iPhone (Continuity Camera)
IMAGE_WIDTH: Final[int] = 1280  # 画像の幅（ピクセル）
IMAGE_HEIGHT: Final[int] = 720  # 画像の高さ（ピクセル）

# 撮影間隔設定
CAPTURE_INTERVAL_SECONDS: Final[int] = 10  # 10秒ごとに撮影

# ローカル保存設定
# このファイルのディレクトリを基準にする
BASE_DIR = Path(__file__).parent
LOCAL_SAVE_DIR: Final[Path] = BASE_DIR / "captured_images"  # 画像保存ディレクトリ
IMAGE_FORMAT: Final[str] = "jpg"  # 画像フォーマット（jpg, png）
IMAGE_QUALITY: Final[int] = 95  # JPEG品質（1-100、高いほど高品質）

# AWS S3設定（環境変数から読み込み、またはここで直接設定）
import os
from dotenv import load_dotenv

# .envファイルから環境変数を読み込み
load_dotenv()

AWS_REGION: Final[str] = os.getenv("AWS_REGION", "ap-northeast-1")  # 東京リージョン
S3_BUCKET_NAME: Final[str] = os.getenv("S3_BUCKET_NAME", "wackathon-2025-trash-images")  # S3バケット名
AWS_ACCESS_KEY_ID: Final[str] = os.getenv("AWS_ACCESS_KEY_ID", "")  # AWSアクセスキー（環境変数推奨）
AWS_SECRET_ACCESS_KEY: Final[str] = os.getenv("AWS_SECRET_ACCESS_KEY", "")  # AWSシークレットキー（環境変数推奨）

# MFA設定
MFA_SERIAL_NUMBER: Final[str] = os.getenv("MFA_SERIAL_NUMBER", "")  # MFAデバイスのARN
MFA_CREDENTIALS_CACHE: Final[Path] = BASE_DIR / ".aws_temp_credentials.json"  # 一時認証情報キャッシュファイル

# ログ設定
LOG_LEVEL: Final[str] = "INFO"  # ログレベル（DEBUG, INFO, WARNING, ERROR）
