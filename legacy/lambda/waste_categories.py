"""
ゴミ分類定義モジュール

AWS Rekognitionから検出されるラベルと、
許可されたゴミ種別のマッピングを定義します。
"""

from typing import Final, Optional

# 許可されたゴミ種別とそれに対応するRekognitionラベル
ALLOWED_WASTE_CATEGORIES: Final[dict[str, list[str]]] = {
    "燃えるゴミ": [
        "Paper",
        "Cardboard",
        "Box",
        "Food",
        "Fruit",
        "Vegetable",
        "Wood",
        "Tissue",
        "Napkin",
        "Document",
        "Letter",
        "Newspaper",
    ],
    "プラスチック": [
        "Plastic",
        "Bottle",
        "Container",
        "Packaging",
        "Bag",
        "Wrapper",
        "Cup",
        "Plate",
        "Cutlery",
        "Straw",
        "PET Bottle",
        "Beverage",
        "Drink",
        "Drink Container",
        "Recycling",
        "Disposable",
        "Food Container",
        "Takeout",
    ],
    "缶・ビン": [
        "Can",
        "Tin",
        "Aluminum",
        "Metal",
        "Glass",
        "Jar",
        "Beverage",
        "Drink",
    ],
    "ペットボトル": [
        "PET Bottle",
        "Plastic Bottle",
        "Water Bottle",
        "Drink Bottle",
        "Bottle",  # 汎用的なボトルもペットボトルとして認識
        "Beverage Bottle",
        "Soda Bottle",
    ],
}

# 禁止されているゴミ（ゴミ箱に入れてはいけないもの）
PROHIBITED_ITEMS: Final[list[str]] = [
    "Battery",
    "Electronics",
    "Phone",
    "Computer",
    "Laptop",
    "Monitor",
    "TV",
    "Appliance",
    "Lamp",
    "Light Bulb",
    "Paint",
    "Chemical",
    "Medicine",
    "Syringe",
    "Hazardous",
]

# 信頼度の閾値（Rekognitionのスコアがこれ以上の場合のみ採用）
CONFIDENCE_THRESHOLD: Final[float] = 60.0  # 検出精度を上げるため閾値を下げる


def get_waste_category(label: str) -> Optional[str]:
    """
    Rekognitionラベルから対応するゴミ種別を取得

    Parameters:
        label: Rekognitionから検出されたラベル名

    Returns:
        対応するゴミ種別名、該当なしの場合はNone
    """
    for category, labels in ALLOWED_WASTE_CATEGORIES.items():
        if label in labels:
            return category
    return None


def is_prohibited(label: str) -> bool:
    """
    禁止アイテムかどうかを判定

    Parameters:
        label: Rekognitionから検出されたラベル名

    Returns:
        禁止アイテムの場合True
    """
    return label in PROHIBITED_ITEMS
