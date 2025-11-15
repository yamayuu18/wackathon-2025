"""
ゴミ分別判定Lambda関数

AWS Rekognitionの検出結果を受け取り、
正しいゴミ分別かどうかを判定して音声メッセージを生成します。
"""

import json
from typing import Any, Final, Optional

from waste_categories import (
    CONFIDENCE_THRESHOLD,
    get_waste_category,
    is_prohibited,
)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda関数のエントリーポイント

    Parameters:
        event: S3イベントとRekognition結果を含む辞書
        context: Lambda実行コンテキスト

    Returns:
        判定結果と音声メッセージを含む辞書
    """
    try:
        # Rekognitionの検出結果を取得
        rekognition_labels = event.get("rekognition_labels", [])

        if not rekognition_labels:
            return create_response(
                is_valid=False,
                message="ゴミが検出されませんでした。もう一度お試しください。",
                detected_items=[],
            )

        # ラベルを解析して判定
        result = validate_waste(rekognition_labels)

        return result

    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return create_response(
            is_valid=False,
            message="システムエラーが発生しました。管理者に連絡してください。",
            detected_items=[],
            error=str(e),
        )


def validate_waste(labels: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Rekognitionラベルを解析してゴミ分別の妥当性を判定

    Parameters:
        labels: Rekognitionから返されたラベルのリスト
              [{"Name": "Bottle", "Confidence": 98.5}, ...]

    Returns:
        判定結果を含む辞書
    """
    detected_items: list[str] = []
    prohibited_found: list[str] = []
    valid_categories: set[str] = set()

    # 各ラベルを解析
    for label_data in labels:
        label_name = label_data.get("Name", "")
        confidence = label_data.get("Confidence", 0.0)

        # 信頼度が閾値以下の場合はスキップ
        if confidence < CONFIDENCE_THRESHOLD:
            continue

        detected_items.append(f"{label_name} ({confidence:.1f}%)")

        # 禁止アイテムチェック
        if is_prohibited(label_name):
            prohibited_found.append(label_name)
            continue

        # ゴミ種別の判定
        category = get_waste_category(label_name)
        if category:
            valid_categories.add(category)

    # 結果の判定とメッセージ生成
    if prohibited_found:
        message = (
            f"申し訳ございません。{', '.join(prohibited_found)}は "
            "このゴミ箱に捨てることができません。"
            "専用の回収場所にお持ちください。"
        )
        return create_response(
            is_valid=False,
            message=message,
            detected_items=detected_items,
            prohibited_items=prohibited_found,
        )

    if valid_categories:
        categories_str = "、".join(valid_categories)
        message = (
            f"ありがとうございます！{categories_str}として正しく分別されています。"
        )
        return create_response(
            is_valid=True,
            message=message,
            detected_items=detected_items,
            categories=list(valid_categories),
        )

    # 該当するゴミ種別が見つからない場合
    message = (
        "このゴミの分別が判定できませんでした。"
        "係員にお尋ねいただくか、分別ガイドをご確認ください。"
    )
    return create_response(
        is_valid=False,
        message=message,
        detected_items=detected_items,
    )


def create_response(
    is_valid: bool,
    message: str,
    detected_items: list[str],
    categories: Optional[list[str]] = None,
    prohibited_items: Optional[list[str]] = None,
    error: Optional[str] = None,
) -> dict[str, Any]:
    """
    Lambda関数のレスポンスを生成

    Parameters:
        is_valid: 分別が正しいかどうか
        message: 音声で読み上げるメッセージ
        detected_items: 検出されたアイテムのリスト
        categories: 判定されたゴミ種別のリスト
        prohibited_items: 検出された禁止アイテムのリスト
        error: エラーメッセージ（エラー時のみ）

    Returns:
        JSON形式のレスポンス辞書
    """
    response = {
        "statusCode": 200,
        "body": json.dumps({
            "is_valid": is_valid,
            "message": message,
            "detected_items": detected_items,
            "categories": categories or [],
            "prohibited_items": prohibited_items or [],
        }, ensure_ascii=False),
    }

    if error:
        response["body"] = json.dumps({
            **json.loads(response["body"]),
            "error": error,
        }, ensure_ascii=False)

    return response
