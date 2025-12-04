import boto3
import json
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

# .env loading is handled in server.py, but for standalone test we might need it.
# Assuming server.py loads .env before importing or using this class.

class Database:
    def __init__(self):
        self.region_name = os.getenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        self.table_name = os.getenv("DYNAMODB_TABLE_NAME", "waste_disposal_history")
        
        # Initialize DynamoDB resource
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region_name)
        self.table = self.dynamodb.Table(self.table_name)
        
        print(f"Database initialized: DynamoDB Table '{self.table_name}' in '{self.region_name}'")

    def insert_record(self, 
                      image_path: str, 
                      result_json: Dict[str, Any], 
                      user_id: Optional[str] = "webapp_user",
                      rejection_reason: Optional[str] = None,
                      timestamp: Optional[str] = None):
        """Insert a new disposal record into DynamoDB."""
        
        # Extract relevant fields
        is_valid = result_json.get("is_valid", False)
        message = result_json.get("message", "")
        detected_items = result_json.get("detected_items", [])
        
        # Timestamp for Sort Key
        if not timestamp:
            timestamp = datetime.now().isoformat()
        
        item = {
            'user_id': user_id,              # Partition Key
            'timestamp': timestamp,          # Sort Key
            'image_path': image_path,
            'detected_items': detected_items,
            'is_valid': is_valid,
            'rejection_reason': rejection_reason,
            'message': message,
            'raw_json': json.dumps(result_json, ensure_ascii=False)
        }
        
        # Remove None values (DynamoDB doesn't like them sometimes, or optional)
        # Actually boto3 handles None as NULL, but empty strings are not allowed in some cases.
        # Let's clean up.
        item = {k: v for k, v in item.items() if v is not None}

        try:
            self.table.put_item(Item=item)
            print(f"✅ DynamoDBに記録しました: {user_id} - {timestamp}")
        except Exception as e:
            print(f"❌ DynamoDB保存エラー: {e}")

    def update_record_message(self, user_id: str, timestamp: str, new_message: str):
        """Update the message of an existing record."""
        try:
            self.table.update_item(
                Key={
                    'user_id': user_id,
                    'timestamp': timestamp
                },
                UpdateExpression="set message = :m",
                ExpressionAttributeValues={
                    ':m': new_message
                }
            )
            print(f"✅ DynamoDBメッセージ更新: {timestamp} -> {new_message}")
        except Exception as e:
            print(f"❌ DynamoDB更新エラー: {e}")

    def get_recent_records(self, user_id: str = "webapp_user", limit: int = 10):
        """Fetch recent records for a user."""
        try:
            response = self.table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id),
                ScanIndexForward=False, # Descending order
                Limit=limit
            )
            return response.get('Items', [])
        except Exception as e:
            print(f"❌ DynamoDB取得エラー: {e}")
            return []
        except Exception as e:
            print(f"❌ DynamoDB取得エラー: {e}")
            return []

    def get_stats(self):
        """
        全データをスキャンして統計情報を取得する
        (デモ用なので全件スキャンでOK)
        """
        try:
            # 全件スキャン (件数が多すぎると遅くなるがデモならOK)
            response = self.table.scan()
            items = response.get('Items', [])
            
            total_ok = 0
            total_ng = 0
            reasons = {}
            daily_stats = {}

            for item in items:
                is_valid = item.get('is_valid', False)
                timestamp = item.get('timestamp', '')
                
                # 日付の抽出 (ISOフォーマット想定: YYYY-MM-DD...)
                date_str = timestamp.split('T')[0] if 'T' in timestamp else 'Unknown'

                if date_str not in daily_stats:
                    daily_stats[date_str] = {'ok': 0, 'ng': 0}

                if is_valid:
                    total_ok += 1
                    daily_stats[date_str]['ok'] += 1
                else:
                    total_ng += 1
                    daily_stats[date_str]['ng'] += 1
                    reason = item.get('rejection_reason')
                    if reason:
                        reasons[reason] = reasons.get(reason, 0) + 1
            
            # 日付順にソート
            sorted_daily = dict(sorted(daily_stats.items()))

            # 最新のログを取得 (タイムスタンプで降順ソートして先頭10件)
            # itemsはscanで取得しているので順序保証なし -> ソートが必要
            sorted_items = sorted(items, key=lambda x: x.get('timestamp', ''), reverse=True)[:10]
            recent_logs = []
            for item in sorted_items:
                recent_logs.append({
                    'timestamp': item.get('timestamp', ''),
                    'is_valid': item.get('is_valid', False),
                    'rejection_reason': item.get('rejection_reason'),
                    'message': item.get('message', '')
                })

            return {
                "total": len(items),
                "ok": total_ok,
                "ng": total_ng,
                "reasons": reasons,
                "daily": sorted_daily,
                "recent_logs": recent_logs
            }
        except Exception as e:
            print(f"❌ 統計取得エラー: {e}")
            return {"total": 0, "ok": 0, "ng": 0, "reasons": {}, "daily": {}, "recent_logs": []}

if __name__ == "__main__":
    # Simple test
    # Note: Requires AWS credentials to be set in environment
    try:
        db = Database()
        print("DynamoDB connection initialized.")
    except Exception as e:
        print(f"Initialization failed: {e}")
