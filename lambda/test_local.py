"""
Lambda関数のローカルテストスクリプト

waste_validator.pyをローカル環境でテストします。
"""

import json
import sys
from typing import Any

from mock_data import ALL_TEST_CASES
from waste_validator import lambda_handler


def print_result(test_name: str, result: dict[str, Any]) -> None:
    """
    テスト結果を見やすく表示

    Parameters:
        test_name: テストケース名
        result: Lambda関数の実行結果
    """
    print(f"\n{'='*60}")
    print(f"テストケース: {test_name}")
    print(f"{'='*60}")

    body = json.loads(result["body"])

    print(f"判定結果: {'✅ OK' if body['is_valid'] else '❌ NG'}")
    print(f"\n音声メッセージ:")
    print(f"  {body['message']}")

    if body["detected_items"]:
        print(f"\n検出されたアイテム:")
        for item in body["detected_items"]:
            print(f"  - {item}")

    if body["categories"]:
        print(f"\n分類されたゴミ種別:")
        for category in body["categories"]:
            print(f"  - {category}")

    if body["prohibited_items"]:
        print(f"\n⚠️ 禁止アイテム:")
        for item in body["prohibited_items"]:
            print(f"  - {item}")

    if "error" in body:
        print(f"\n❌ エラー: {body['error']}")


def run_all_tests() -> None:
    """全てのテストケースを実行"""
    print("Lambda関数ローカルテスト開始")
    print("="*60)

    passed = 0
    failed = 0

    for test_name, test_data in ALL_TEST_CASES.items():
        try:
            result = lambda_handler(test_data, None)
            print_result(test_name, result)
            passed += 1
        except Exception as e:
            print(f"\n❌ テスト '{test_name}' でエラー発生: {str(e)}")
            failed += 1

    # サマリー表示
    print(f"\n{'='*60}")
    print(f"テスト結果サマリー")
    print(f"{'='*60}")
    print(f"✅ 成功: {passed}")
    print(f"❌ 失敗: {failed}")
    print(f"合計: {passed + failed}")


def run_single_test(test_name: str) -> None:
    """
    特定のテストケースを実行

    Parameters:
        test_name: テストケース名
    """
    if test_name not in ALL_TEST_CASES:
        print(f"❌ テストケース '{test_name}' が見つかりません")
        print(f"\n利用可能なテストケース:")
        for name in ALL_TEST_CASES.keys():
            print(f"  - {name}")
        return

    test_data = ALL_TEST_CASES[test_name]
    result = lambda_handler(test_data, None)
    print_result(test_name, result)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # コマンドライン引数で指定されたテストケースを実行
        test_name = sys.argv[1]
        run_single_test(test_name)
    else:
        # 全テストケースを実行
        run_all_tests()
