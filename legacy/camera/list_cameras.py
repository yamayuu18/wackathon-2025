import cv2

def list_cameras(max_check=10):
    print("カメラデバイスを検索中...")
    available_cameras = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print(f"[OK] Device ID {i}: カメラを開けました ({int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})")
                available_cameras.append(i)
            else:
                print(f"[NG] Device ID {i}: カメラは開けましたが、映像が取得できませんでした")
            cap.release()
        else:
            pass
            # print(f"[--] Device ID {i}: カメラが見つかりません")

    if not available_cameras:
        print("\n利用可能なカメラが見つかりませんでした。")
    else:
        print("\n=== 検出されたカメラ ===")
        print(f"利用可能な Device ID: {available_cameras}")
        print("iPhone連携カメラを使用する場合、通常は '0' 以外（'1' や '2'）になることが多いです。")
        print("config.py の CAMERA_DEVICE_ID をこの番号に変更してください。")

if __name__ == "__main__":
    list_cameras()
