"""
ローカルテスト用スクリプト

AWS Lambda環境を模倣してwaste_validator.pyを実行します。
OpenAI APIの呼び出しはモック化されます。
"""

import json
import sys
from unittest.mock import MagicMock, patch

# モジュールパスを追加
sys.path.append(".")

import waste_validator

# テストケース定義
TEST_CASES = [
    {
        "name": "正常系: ペットボトル（ラベルなし）",
        "mock_response": {
            "is_valid": True,
            "message": "ありがとうございます！ペットボトルとして正しく分別されています。",
            "detected_items": ["Plastic Bottle"],
            "categories": ["ペットボトル"],
            "prohibited_items": [],
            "label_removed": True,
            "is_full": False,
        },
    },
    {
        "name": "異常系: ペットボトル（ラベルあり）",
        "mock_response": {
            "is_valid": False,
            "message": "ペットボトルのラベルを剥がしてください。",
            "detected_items": ["Plastic Bottle"],
            "categories": ["ペットボトル"],
            "prohibited_items": [],
            "label_removed": False,
            "is_full": False,
        },
    },
    {
        "name": "異常系: 禁止物（電池）",
        "mock_response": {
            "is_valid": False,
            "message": "電池は捨てられません。",
            "detected_items": ["Battery"],
            "categories": [],
            "prohibited_items": ["Battery"],
            "label_removed": False,
            "is_full": False,
        },
    },
    {
        "name": "異常系: ゴミ箱満杯",
        "mock_response": {
            "is_valid": True,
            "message": "ありがとうございます。ゴミ箱がいっぱいになってきました。",
            "detected_items": ["Paper"],
            "categories": ["燃えるゴミ"],
            "prohibited_items": [],
            "label_removed": False,
            "is_full": True,
        },
    },
]


def run_tests():
    print("=== ローカルテスト開始 ===")

    # モックの設定
    with patch("waste_validator.s3") as mock_s3, patch(
        "waste_validator.openai_client"
    ) as mock_openai:

        # S3のモック設定
        mock_s3.get_object.return_value = {
            "Body": MagicMock(read=lambda: b"dummy_image_data")
        }
        mock_s3.put_object.return_value = {}

        # OpenAI TTSのモック設定
        mock_openai.generate_speech.return_value = b"dummy_audio_data"

        for i, case in enumerate(TEST_CASES):
            print(f"\n--- Test Case {i+1}: {case['name']} ---")

            # OpenAI Visionのモック設定
            mock_openai.analyze_image.return_value = case["mock_response"]

            # ダミーイベント
            event = {
                "Records": [
                    {
                        "s3": {
                            "bucket": {"name": "test-bucket"},
                            "object": {"key": "test.jpg"},
                        }
                    }
                ]
            }

            # 実行
            response = waste_validator.lambda_handler(event, None)
            body = json.loads(response["body"])

            # 検証
            print(f"Status Code: {response['statusCode']}")
            print(f"Is Valid: {body['is_valid']}")
            print(f"Message: {body['message']}")
            print(f"Audio URL: {body.get('audio_url')}")
            
            if "label_removed" in body:
                print(f"Label Removed: {body['label_removed']}")
            if "is_full" in body:
                print(f"Is Full: {body['is_full']}")

            # アサーション
            expected = case["mock_response"]
            if body["is_valid"] != expected["is_valid"]:
                print(f"[FAIL] is_valid mismatch. Expected {expected['is_valid']}")
            elif body["message"] != expected["message"]:
                print(f"[FAIL] message mismatch.")
            else:
                print("[PASS]")

    print("\n=== テスト完了 ===")


if __name__ == "__main__":
    run_tests()
