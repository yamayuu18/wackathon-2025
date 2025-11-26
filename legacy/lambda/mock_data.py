"""
Rekognition DetectLabels APIのモックデータ

テスト用のRekognitionレスポンスサンプルを提供します。
"""

from typing import Any, Final

# 正常系: プラスチックボトル
VALID_PLASTIC_BOTTLE: Final[dict[str, Any]] = {
    "rekognition_labels": [
        {"Name": "Bottle", "Confidence": 98.5},
        {"Name": "Plastic", "Confidence": 95.2},
        {"Name": "Container", "Confidence": 89.7},
    ]
}

# 正常系: 紙ゴミ
VALID_PAPER: Final[dict[str, Any]] = {
    "rekognition_labels": [
        {"Name": "Paper", "Confidence": 99.1},
        {"Name": "Document", "Confidence": 92.3},
        {"Name": "Cardboard", "Confidence": 88.5},
    ]
}

# 正常系: 缶
VALID_CAN: Final[dict[str, Any]] = {
    "rekognition_labels": [
        {"Name": "Can", "Confidence": 97.8},
        {"Name": "Aluminum", "Confidence": 94.5},
        {"Name": "Beverage", "Confidence": 91.2},
    ]
}

# 異常系: 禁止アイテム（バッテリー）
INVALID_BATTERY: Final[dict[str, Any]] = {
    "rekognition_labels": [
        {"Name": "Battery", "Confidence": 96.3},
        {"Name": "Electronics", "Confidence": 88.9},
    ]
}

# 異常系: 禁止アイテム（電子機器）
INVALID_ELECTRONICS: Final[dict[str, Any]] = {
    "rekognition_labels": [
        {"Name": "Phone", "Confidence": 98.7},
        {"Name": "Electronics", "Confidence": 95.4},
        {"Name": "Computer", "Confidence": 87.2},
    ]
}

# 異常系: 検出なし
NO_DETECTION: Final[dict[str, Any]] = {
    "rekognition_labels": []
}

# 異常系: 低信頼度
LOW_CONFIDENCE: Final[dict[str, Any]] = {
    "rekognition_labels": [
        {"Name": "Bottle", "Confidence": 45.2},
        {"Name": "Plastic", "Confidence": 38.7},
    ]
}

# 複合系: 複数種別のゴミ
MIXED_WASTE: Final[dict[str, Any]] = {
    "rekognition_labels": [
        {"Name": "Bottle", "Confidence": 97.5},
        {"Name": "Paper", "Confidence": 93.2},
        {"Name": "Can", "Confidence": 89.8},
        {"Name": "Plastic", "Confidence": 88.4},
    ]
}

# 不明なゴミ
UNKNOWN_WASTE: Final[dict[str, Any]] = {
    "rekognition_labels": [
        {"Name": "Unknown Object", "Confidence": 85.3},
        {"Name": "Thing", "Confidence": 72.1},
    ]
}

# 全テストケース
ALL_TEST_CASES: Final[dict[str, dict[str, Any]]] = {
    "valid_plastic_bottle": VALID_PLASTIC_BOTTLE,
    "valid_paper": VALID_PAPER,
    "valid_can": VALID_CAN,
    "invalid_battery": INVALID_BATTERY,
    "invalid_electronics": INVALID_ELECTRONICS,
    "no_detection": NO_DETECTION,
    "low_confidence": LOW_CONFIDENCE,
    "mixed_waste": MIXED_WASTE,
    "unknown_waste": UNKNOWN_WASTE,
}
