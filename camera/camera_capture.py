"""PCのカメラから定期的に画像を取得してローカルに保存するプログラム

このスクリプトは、OpenCVを使用してPCのカメラから画像を取得し、
設定された間隔（デフォルト5秒）でタイムスタンプ付きの画像をローカルに保存します。

Usage:
    python camera_capture.py
"""

import cv2
import os
import time
from datetime import datetime
from typing import Optional
import traceback

import config


class CameraCapture:
    """カメラ撮影を管理するクラス"""

    def __init__(self) -> None:
        """カメラキャプチャの初期化

        Parameters:
            なし

        Returns:
            なし
        """
        self.camera: Optional[cv2.VideoCapture] = None
        self.save_dir: str = config.LOCAL_SAVE_DIR
        self._ensure_save_directory()

    def _ensure_save_directory(self) -> None:
        """保存ディレクトリが存在することを確認、なければ作成

        Parameters:
            なし

        Returns:
            なし
        """
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
            print(f"Created directory: {self.save_dir}")

    def initialize_camera(self) -> bool:
        """カメラデバイスを初期化

        Parameters:
            なし

        Returns:
            bool: 初期化成功時True、失敗時False
        """
        try:
            self.camera = cv2.VideoCapture(config.CAMERA_DEVICE_ID)

            if not self.camera.isOpened():
                print(f"Error: Cannot open camera device {config.CAMERA_DEVICE_ID}")
                return False

            # カメラの解像度を設定
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.IMAGE_WIDTH)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.IMAGE_HEIGHT)

            print(f"Camera initialized: Device {config.CAMERA_DEVICE_ID}, "
                  f"Resolution {config.IMAGE_WIDTH}x{config.IMAGE_HEIGHT}")
            return True

        except Exception as e:
            print(f"Error initializing camera: {e}")
            traceback.print_exc()
            return False

    def capture_image(self) -> Optional[str]:
        """カメラから画像を取得してローカルに保存

        Parameters:
            なし

        Returns:
            Optional[str]: 保存した画像のファイルパス、失敗時None
        """
        if self.camera is None or not self.camera.isOpened():
            print("Error: Camera is not initialized")
            return None

        try:
            # カメラから1フレーム取得
            ret, frame = self.camera.read()

            if not ret:
                print("Error: Failed to capture frame")
                return None

            # タイムスタンプ付きファイル名を生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"capture_{timestamp}.{config.IMAGE_FORMAT}"
            filepath = os.path.join(self.save_dir, filename)

            # 画像を保存
            if config.IMAGE_FORMAT.lower() == "jpg":
                cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, config.IMAGE_QUALITY])
            else:
                cv2.imwrite(filepath, frame)

            print(f"Image saved: {filepath}")
            return filepath

        except Exception as e:
            print(f"Error capturing image: {e}")
            traceback.print_exc()
            return None

    def start_continuous_capture(self) -> None:
        """設定された間隔で連続撮影を開始

        Parameters:
            なし

        Returns:
            なし
        """
        print(f"Starting continuous capture (interval: {config.CAPTURE_INTERVAL_SECONDS} seconds)")
        print("Press Ctrl+C to stop")

        try:
            while True:
                # 画像を撮影
                filepath = self.capture_image()

                if filepath:
                    print(f"Waiting {config.CAPTURE_INTERVAL_SECONDS} seconds until next capture...")

                # 設定された間隔だけ待機
                time.sleep(config.CAPTURE_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nCapture stopped by user")
        except Exception as e:
            print(f"Error during continuous capture: {e}")
            traceback.print_exc()

    def release(self) -> None:
        """カメラリソースを解放

        Parameters:
            なし

        Returns:
            なし
        """
        if self.camera is not None:
            self.camera.release()
            print("Camera released")


def main() -> None:
    """メイン関数

    Parameters:
        なし

    Returns:
        なし
    """
    print("=" * 50)
    print("Camera Capture Program")
    print("=" * 50)

    # CameraCaptureインスタンスを作成
    capture = CameraCapture()

    # カメラを初期化
    if not capture.initialize_camera():
        print("Failed to initialize camera. Exiting...")
        return

    try:
        # 連続撮影を開始
        capture.start_continuous_capture()
    finally:
        # 終了時にカメラを解放
        capture.release()


if __name__ == "__main__":
    main()
