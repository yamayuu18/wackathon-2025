import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

DB_PATH = Path(__file__).parent / "waste_data.db"

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS disposal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    user_id TEXT,
                    image_path TEXT,
                    detected_items TEXT,
                    is_valid BOOLEAN,
                    message TEXT,
                    raw_json TEXT
                )
            """)
            conn.commit()

    def insert_record(self, 
                      image_path: str, 
                      result_json: Dict[str, Any], 
                      user_id: Optional[str] = None):
        """Insert a new disposal record."""
        
        # Extract relevant fields from the result JSON
        is_valid = result_json.get("is_valid", False)
        message = result_json.get("message", "")
        detected_items = json.dumps(result_json.get("detected_items", []), ensure_ascii=False)
        raw_json_str = json.dumps(result_json, ensure_ascii=False)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO disposal_history 
                (user_id, image_path, detected_items, is_valid, message, raw_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, image_path, detected_items, is_valid, message, raw_json_str))
            conn.commit()
            print(f"✅ DBに記録しました: ID={cursor.lastrowid}")

    def get_recent_records(self, limit: int = 10):
        """Fetch recent records."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM disposal_history 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

if __name__ == "__main__":
    # Simple test
    db = Database()
    print(f"Database initialized at {db.db_path}")
