"""MFA認証を使用したカメラ画像のS3アップロードスクリプト

STS (Security Token Service) を使用して一時認証情報を取得し、
S3にアップロードします。
"""

import json
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
    IMAGE_FORMAT,
    IMAGE_HEIGHT,
    IMAGE_QUALITY,
    IMAGE_WIDTH,
    LOCAL_SAVE_DIR,
    MFA_CREDENTIALS_CACHE,
    MFA_SERIAL_NUMBER,
    S3_BUCKET_NAME,
)


class MFACameraToS3Uploader:
    """MFA認証を使用したカメラ画像のS3アップローダー"""

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

        # 一時認証情報（STSで取得）
        self.temp_credentials: Optional[dict] = None

        print(f"✅ カメラ初期化成功")

    def save_credentials(self) -> bool:
        """
        一時認証情報をファイルに保存

        Returns:
            保存成功時True、失敗時False
        """
        if not self.temp_credentials:
            return False

        try:
            cache_path = Path(MFA_CREDENTIALS_CACHE)
            cache_path.parent.mkdir(parents=True, exist_ok=True)

            # datetimeをISO形式の文字列に変換
            credentials_data = {
                "AccessKeyId": self.temp_credentials["AccessKeyId"],
                "SecretAccessKey": self.temp_credentials["SecretAccessKey"],
                "SessionToken": self.temp_credentials["SessionToken"],
                "Expiration": self.temp_credentials["Expiration"].isoformat(),
            }

            with open(cache_path, "w") as f:
                json.dump(credentials_data, f, indent=2)

            print(f"💾 認証情報をキャッシュに保存: {cache_path}")
            return True

        except Exception as e:
            print(f"⚠️ 認証情報の保存に失敗: {str(e)}")
            return False

    def load_credentials(self) -> bool:
        """
        ファイルから一時認証情報を読み込み

        Returns:
            読み込み成功時True、失敗時False
        """
        cache_path = Path(MFA_CREDENTIALS_CACHE)

        if not cache_path.exists():
            return False

        try:
            with open(cache_path, "r") as f:
                credentials_data = json.load(f)

            # ISO形式の文字列をdatetimeに変換
            expiration = datetime.fromisoformat(credentials_data["Expiration"])

            self.temp_credentials = {
                "AccessKeyId": credentials_data["AccessKeyId"],
                "SecretAccessKey": credentials_data["SecretAccessKey"],
                "SessionToken": credentials_data["SessionToken"],
                "Expiration": expiration,
            }

            return True

        except Exception as e:
            print(f"⚠️ 認証情報の読み込みに失敗: {str(e)}")
            return False

    def is_credentials_valid(self) -> bool:
        """
        一時認証情報が有効かチェック

        Returns:
            有効な場合True、無効または存在しない場合False
        """
        if not self.temp_credentials:
            return False

        try:
            expiration = self.temp_credentials["Expiration"]
            # 現在時刻より5分以上未来なら有効
            time_remaining = (expiration - datetime.now(expiration.tzinfo)).total_seconds()
            return time_remaining > 300  # 5分以上残っている

        except Exception:
            return False

    def get_mfa_session_token(self, mfa_code: str) -> bool:
        """
        MFA認証で一時認証情報を取得

        Parameters:
            mfa_code: 6桁のMFAコード

        Returns:
            成功時True、失敗時False
        """
        try:
            # STSクライアントの作成
            sts_client = boto3.client(
                "sts",
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_REGION,
            )

            print(f"🔐 MFA認証中...")

            # 一時認証情報の取得（12時間有効）
            response = sts_client.get_session_token(
                SerialNumber=MFA_SERIAL_NUMBER,
                TokenCode=mfa_code,
                DurationSeconds=43200,  # 12時間
            )

            self.temp_credentials = response["Credentials"]

            print(f"✅ MFA認証成功")
            print(
                f"   有効期限: {self.temp_credentials['Expiration'].strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # 認証情報をキャッシュに保存
            self.save_credentials()

            return True

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            print(f"❌ MFA認証エラー [{error_code}]: {error_message}")
            return False

        except Exception as e:
            print(f"❌ 予期しないエラー: {str(e)}")
            return False

    def get_s3_client(self):
        """
        一時認証情報を使用してS3クライアントを作成

        Returns:
            S3クライアント、または認証情報がない場合はNone
        """
        if not self.temp_credentials:
            print("❌ 一時認証情報がありません。先にMFA認証を実行してください。")
            return None

        try:
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=self.temp_credentials["AccessKeyId"],
                aws_secret_access_key=self.temp_credentials["SecretAccessKey"],
                aws_session_token=self.temp_credentials["SessionToken"],
                region_name=AWS_REGION,
            )
            return s3_client

        except Exception as e:
            print(f"❌ S3クライアント作成エラー: {str(e)}")
            return None

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
        s3_client = self.get_s3_client()
        if not s3_client:
            return False

        filename = Path(filepath).name
        s3_key = f"images/{filename}"

        try:
            s3_client.upload_file(
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
        print("カメラ撮影 & S3アップロード開始（MFA認証）")
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
    uploader: Optional[MFACameraToS3Uploader] = None

    try:
        # 環境変数のチェック
        if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
            print("❌ エラー: AWS認証情報が設定されていません")
            print("   .envファイルを確認してください")
            return 1

        if not MFA_SERIAL_NUMBER:
            print("❌ エラー: MFA_SERIAL_NUMBERが設定されていません")
            print("   .envファイルにMFAデバイスのARNを設定してください")
            print("   例: MFA_SERIAL_NUMBER=arn:aws:iam::438632968703:mfa/D_yamapan")
            return 1

        # アップローダーを初期化
        uploader = MFACameraToS3Uploader()

        # キャッシュから認証情報を読み込み
        print("\n🔍 キャッシュされた認証情報を確認中...")
        if uploader.load_credentials() and uploader.is_credentials_valid():
            print("✅ 有効な認証情報をキャッシュから復元しました")
            expiration = uploader.temp_credentials["Expiration"]
            print(f"   有効期限: {expiration.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            # キャッシュが無効な場合、MFA認証を実行
            print("⚠️ 有効な認証情報がありません。MFA認証が必要です。")
            print("\n📱 MFAアプリで生成された6桁のコードを入力してください")
            mfa_code = input("MFAコード: ").strip()

            if len(mfa_code) != 6 or not mfa_code.isdigit():
                print("❌ エラー: MFAコードは6桁の数字である必要があります")
                return 1

            # MFA認証で一時認証情報を取得
            if not uploader.get_mfa_session_token(mfa_code):
                return 1

        # 連続実行
        import time
        from config import CAPTURE_INTERVAL_SECONDS

        print(f"\n🚀 連続撮影モードを開始します（間隔: {CAPTURE_INTERVAL_SECONDS}秒）")
        print("   Ctrl+C で停止します")

        while True:
            success = uploader.run_once()
            if not success:
                print("⚠️ エラーが発生しましたが、実行を継続します...")
            
            time.sleep(CAPTURE_INTERVAL_SECONDS)

        return 0

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
