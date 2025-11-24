from database import Database
import os

def test_database():
    print("🧪 DBテスト開始...")
    
    # DB初期化
    db = Database()
    
    # テストデータ
    test_data = {
        "is_valid": False,
        "message": "テストメッセージです",
        "detected_items": ["pet_bottle", "label"],
        "raw_data": "test"
    }
    
    # 挿入テスト
    print("📝 レコード挿入テスト...")
    db.insert_record(
        image_path="test/image.jpg",
        result_json=test_data,
        user_id="test_user"
    )
    
    # 取得テスト
    print("🔍 レコード取得テスト...")
    records = db.get_recent_records(limit=1)
    
    if not records:
        print("❌ レコードが見つかりません")
        return
        
    latest = records[0]
    print(f"✅ 最新レコード: {latest['timestamp']}")
    print(f"   Message: {latest['message']}")
    print(f"   Items: {latest['detected_items']}")
    
    assert latest['message'] == "テストメッセージです"
    print("🎉 テスト完了: 正常に動作しています")

if __name__ == "__main__":
    test_database()
