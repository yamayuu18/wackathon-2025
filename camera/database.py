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
                      rejection_reason: Optional[str] = None):
        """Insert a new disposal record into DynamoDB."""
        
        # Extract relevant fields
        is_valid = result_json.get("is_valid", False)
        message = result_json.get("message", "")
        detected_items = result_json.get("detected_items", [])
        
        # Timestamp for Sort Key
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

if __name__ == "__main__":
    # Simple test
    # Note: Requires AWS credentials to be set in environment
    try:
        db = Database()
        print("DynamoDB connection initialized.")
    except Exception as e:
        print(f"Initialization failed: {e}")
