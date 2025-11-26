import os
import json
import time
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, send_file, Response

import boto3
from dotenv import load_dotenv

from voicevox_client import VoicevoxClient
from database import Database

# 設定読み込み
load_dotenv()
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "wackathon-2025-trash-images")
VOICE_BUCKET_NAME = os.getenv("VOICE_BUCKET_NAME", "wackathon-2025-voice-responses")

import sys
# config.pyをインポートできるようにパスを追加
sys.path.append(str(Path(__file__).parent))

from config import MFA_CREDENTIALS_CACHE

# アプリ設定
app = Flask(__name__)
voicevox = VoicevoxClient()

def get_s3_client():
    """キャッシュされた認証情報を使用してS3クライアントを作成"""
    try:
        if not MFA_CREDENTIALS_CACHE.exists():
            print("⚠️ 認証情報キャッシュが見つかりません")
            return None
            
        with open(MFA_CREDENTIALS_CACHE, "r") as f:
            creds = json.load(f)
            
        return boto3.client(
            "s3",
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
            region_name=AWS_REGION
        )
    except Exception as e:
        print(f"⚠️ S3クライアント作成エラー: {e}")
        return None

# 初期クライアント（起動時にチェックはしない、スレッド内でやる）
# s3 = get_s3_client()

# 状態管理
current_state = {
    "last_processed_key": None,
    "current_audio_file": None,
    "message": "待機中...",
    "timestamp": None
}

# このファイルのディレクトリを基準にする
BASE_DIR = Path(__file__).parent
AUDIO_DIR = BASE_DIR / "static" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

def poll_s3_results():
    """バックグラウンドでS3を監視するスレッド"""
    print("🚀 S3監視スレッドを開始しました")
    s3_client = None

    # DB初期化
    db = Database()
    
    while True:
        try:
            # クライアントがない、または再生成が必要な場合
            if s3_client is None:
                s3_client = get_s3_client()
                if s3_client is None:
                    # 認証情報がまだない場合は待機
                    print("Waiting for fresh credentials...")
                    time.sleep(5)
                    continue
                print("✅ S3クライアントをロードしました")

            # 最新のJSON結果を取得
            response = s3_client.list_objects_v2(
                Bucket=VOICE_BUCKET_NAME,
                Prefix="results/"
            )
            
            if "Contents" not in response:
                time.sleep(1)
                continue

            # 更新日時でソートして最新を取得
            latest_obj = sorted(
                response["Contents"], 
                key=lambda x: x["LastModified"], 
                reverse=True
            )[0]
            
            key = latest_obj["Key"]
            
            # 初回起動時は最新のキーを記録するだけで処理はしない
            if current_state["last_processed_key"] is None:
                current_state["last_processed_key"] = key
                print(f"✅ 初期状態を設定: 最新のキーは {key} です（これは再生しません）")
                time.sleep(1)
                continue
            
            # 新しいファイルが見つかった場合
            if key != current_state["last_processed_key"]:
                print(f"📥 新しい結果を検出: {key}")
                
                # JSONをダウンロード
                obj = s3_client.get_object(Bucket=VOICE_BUCKET_NAME, Key=key)
                data = json.loads(obj["Body"].read().decode("utf-8"))
                
                # DBに記録
                try:
                    # S3キーから画像パスを推測（簡易的）
                    # 実際にはLambdaの結果に画像パスを含めるのがベストだが、今はキーを記録
                    db.insert_record(image_path=key, result_json=data)
                except Exception as e:
                    print(f"⚠️ DB保存エラー: {e}")

                message = data.get("message", "")
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if message:
                    print(f"🗣️ 音声生成開始: {message}")
                    # Voicevoxで音声生成
                    # 話者ID 3: ずんだもん（ノーマル）
                    audio_data = voicevox.generate_audio(message, speaker_id=3)
                    
                    if audio_data:
                        # ファイル保存
                        filename = f"voice_{int(time.time())}.wav"
                        filepath = AUDIO_DIR / filename
                        with open(filepath, "wb") as f:
                            f.write(audio_data)
                        
                        # 状態更新
                        current_state["last_processed_key"] = key
                        current_state["current_audio_file"] = filename
                        current_state["message"] = message
                        current_state["timestamp"] = timestamp
                        print(f"✅ 音声生成完了: {filename}")
                        
                        # Macで音声を再生
                        try:
                            print("🔊 Macで再生中...")
                            subprocess.run(["afplay", str(filepath)], check=False)
                        except Exception as e:
                            print(f"⚠️ 音声再生エラー: {e}")
                    else:
                        print("❌ 音声生成失敗")
                
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ ポーリングエラー: {error_msg}")
            
            # トークン期限切れやアクセス権限エラーの場合はクライアントを破棄して再取得を試みる
            if "ExpiredToken" in error_msg or "AccessDenied" in error_msg:
                print("🔄 認証情報が無効です。再読み込みを待機します...")
                s3_client = None
                time.sleep(5)
        
        time.sleep(1)  # 1秒間隔でポーリング

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/status")
def status():
    """現在の状態を返す（ポーリング用）"""
    return jsonify({
        "audio_file": current_state["current_audio_file"],
        "message": current_state["message"],
        "timestamp": current_state["timestamp"]
    })

@app.route("/audio/<filename>")
def get_audio(filename):
    """音声ファイルを配信"""
    return send_file(AUDIO_DIR / filename, mimetype="audio/wav")

if __name__ == "__main__":
    # 監視スレッド起動
    thread = threading.Thread(target=poll_s3_results, daemon=True)
    thread.start()
    
    # サーバー起動 (全インターフェースで待受)
    app.run(host="0.0.0.0", port=5001, debug=False)
