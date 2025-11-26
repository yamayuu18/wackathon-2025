import boto3
import time
from datetime import datetime, timedelta
import sys
import os
from pathlib import Path
import json

# Add parent directory to path to import config
sys.path.append(str(Path(__file__).parent.parent))
from camera.config import MFA_CREDENTIALS_CACHE

AWS_REGION = "ap-northeast-1"
LOG_GROUP_NAME = "/aws/lambda/wackathon-waste-recognition"

def get_boto3_client(service_name):
    """Get boto3 client using cached MFA credentials"""
    if not MFA_CREDENTIALS_CACHE.exists():
        print("⚠️ No cached credentials found. Please run camera_to_s3_mfa.py first.")
        return None
        
    with open(MFA_CREDENTIALS_CACHE, "r") as f:
        creds = json.load(f)
        
    return boto3.client(
        service_name,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=AWS_REGION
    )

def fetch_logs():
    client = get_boto3_client("logs")
    if not client:
        return

    print(f"🔍 Fetching logs from {LOG_GROUP_NAME}...")
    
    try:
        # Get the latest log stream
        response = client.describe_log_streams(
            logGroupName=LOG_GROUP_NAME,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        
        if not response['logStreams']:
            print("❌ No log streams found.")
            return

        log_stream_name = response['logStreams'][0]['logStreamName']
        print(f"📄 Latest Log Stream: {log_stream_name}")
        
        # Get log events
        logs = client.get_log_events(
            logGroupName=LOG_GROUP_NAME,
            logStreamName=log_stream_name,
            limit=20,
            startFromHead=False
        )
        
        print("\n--- Latest Logs ---")
        for event in logs['events']:
            timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
            message = event['message'].strip()
            print(f"[{timestamp}] {message}")
            
    except Exception as e:
        print(f"❌ Error fetching logs: {e}")

if __name__ == "__main__":
    fetch_logs()
