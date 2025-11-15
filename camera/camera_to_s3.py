"""カメラ画像をS3にアップロードするスクリプト

定期的にカメラで撮影した画像をAWS S3にアップロードします。
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import boto3
import cv2
from botocore.exceptions import ClientError, NoCredentialsError

from config import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    CAMERA_DEVICE_ID,
    CAPTURE_INTERVAL_SECONDS,
    IMAGE_FORMAT,
    IMAGE_HEIGHT,
    IMAGE_QUALITY,
    IMAGE_WIDTH,
    LOCAL_SAVE_DIR,
    S3_BUCKET_NAME,
)


class CameraToS3Uploader:
    """カメラ画像のS3アップローダー"""

    def __init__(self) -> None:
        """初期化処理"""
        # カメラの初期化
        self.camera = cv2.VideoCapture(CAMERA_DEVICE_ID)
        if not self.camera.isOpened():
            raise RuntimeError(f"カメラデバイス {CAMERA_DEVICE_ID} を開けません")

        # カメラ設定
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, IMAGE_WIDTH)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, IMAGE_HEIGHT)

        # ローカル保存ディレクトリの作成
        self.local_dir = Path(LOCAL_SAVE_DIR)
        self.local_dir.mkdir(parents=True, exist_ok=True)

        # S3クライアントの初期化
        try:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION,
            )
            print(f"✅ S3クライアント初期化成功 (リージョン: {AWS_REGION})")
        except NoCredentialsError:
            raise RuntimeError("AWS認証情報が見つかりません。config.pyを確認してください")

    def capture_image(self) -> Optional[str]:
        """
        カメラで画像をキャプチャしてローカルに保存

        Returns:
            保存した画像のファイルパス、失敗時はNone
        """
        ret, frame = self.camera.read()
        if not ret:
            print("❌ カメラからの画像取得に失敗しました")
            return None

        # タイムスタンプ付きファイル名を生成
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trash_image_{timestamp}.{IMAGE_FORMAT}"
        filepath = self.local_dir / filename

        # 画像を保存
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, IMAGE_QUALITY]
        success = cv2.imwrite(str(filepath), frame, encode_params)

        if success:
            print(f"✅ 画像をキャプチャ: {filepath}")
            return str(filepath)
        else:
            print(f"❌ 画像の保存に失敗: {filepath}")
            return None

    def upload_to_s3(self, filepath: str) -> bool:
        """
        画像をS3にアップロード

        Parameters:
            filepath: アップロードする画像のローカルパス

        Returns:
            アップロード成功時True、失敗時False
        """
        filename = Path(filepath).name
        s3_key = f"images/{filename}"

        try:
            self.s3_client.upload_file(
                filepath,
                S3_BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": f"image/{IMAGE_FORMAT}"},
            )
            print(f"✅ S3アップロード成功: s3://{S3_BUCKET_NAME}/{s3_key}")
            return True

        except FileNotFoundError:
            print(f"❌ ファイルが見つかりません: {filepath}")
            return False

        except NoCredentialsError:
            print("❌ AWS認証情報が無効です")
            return False

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            print(f"❌ S3アップロードエラー [{error_code}]: {error_message}")
            return False

        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")
            return False

    def run_once(self) -> bool:
        """
        1回だけ撮影→アップロードを実行（テスト用）

        Returns:
            成功時True、失敗時False
        """
        print("\n" + "=" * 60)
        print("カメラ撮影 & S3アップロード開始")
        print("=" * 60)

        # 画像をキャプチャ
        filepath = self.capture_image()
        if not filepath:
            return False

        # S3にアップロード
        success = self.upload_to_s3(filepath)

        if success:
            print("\n✅ 処理が正常に完了しました")
        else:
            print("\n❌ 処理中にエラーが発生しました")

        return success

    def cleanup(self) -> None:
        """リソースの解放"""
        if self.camera.isOpened():
            self.camera.release()
            print("✅ カメラをクローズしました")


def main() -> int:
    """メイン処理"""
    uploader: Optional[CameraToS3Uploader] = None

    try:
        # アップローダーを初期化
        uploader = CameraToS3Uploader()

        # テスト実行（1回だけ撮影→アップロード）
        success = uploader.run_once()

        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n\n⚠️ ユーザーによって中断されました")
        return 130

    except Exception as e:
        print(f"\n❌ 致命的なエラー: {str(e)}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1

    finally:
        if uploader:
            uploader.cleanup()


if __name__ == "__main__":
    sys.exit(main())
