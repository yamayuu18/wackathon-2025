import os
import sys
import json
import boto3
from pathlib import Path
from dotenv import load_dotenv

# 親ディレクトリの.envを読み込む
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
MFA_SERIAL_NUMBER = os.getenv("MFA_SERIAL_NUMBER")
FUNCTION_NAME = "wackathon-waste-recognition"
ZIP_FILE = "waste_recognition.zip"

def get_mfa_credentials():
    """MFA認証を行って一時クレデンシャルを取得する"""
    if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, MFA_SERIAL_NUMBER]):
        print("❌ エラー: .envファイルに必要な環境変数が設定されていません。")
        return None

    print(f"🔐 MFA認証が必要です。デバイス: {MFA_SERIAL_NUMBER}")
    mfa_code = input("MFAコード(6桁)を入力してください: ").strip()

    sts = boto3.client(
        "sts",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

    try:
        response = sts.get_session_token(
            SerialNumber=MFA_SERIAL_NUMBER,
            TokenCode=mfa_code,
            DurationSeconds=900  # 15分
        )
        return response["Credentials"]
    except Exception as e:
        print(f"❌ MFA認証失敗: {e}")
        return None

def deploy_lambda(credentials):
    """Lambda関数を更新する"""
    print(f"🚀 Lambda関数 '{FUNCTION_NAME}' を更新中...")
    
    lambda_client = boto3.client(
        "lambda",
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=AWS_REGION
    )

    try:
        with open(ZIP_FILE, "rb") as f:
            zip_content = f.read()

        response = lambda_client.update_function_code(
            FunctionName=FUNCTION_NAME,
            ZipFile=zip_content
        )
        
        print(f"✅ デプロイ完了! (Version: {response['Version']})")
        print(f"   Last Modified: {response['LastModified']}")
        return True

    except Exception as e:
        print(f"❌ デプロイ失敗: {e}")
        return False

if __name__ == "__main__":
    if not Path(ZIP_FILE).exists():
        print(f"❌ エラー: {ZIP_FILE} が見つかりません。")
        sys.exit(1)

    creds = get_mfa_credentials()
    if creds:
        deploy_lambda(creds)
