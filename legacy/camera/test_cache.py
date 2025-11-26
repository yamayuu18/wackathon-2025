"""認証情報キャッシュ機能のテストスクリプト

このスクリプトは、キャッシュ機能が正しく動作するかを確認します。
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import MFA_CREDENTIALS_CACHE


def create_test_cache():
    """テスト用の認証情報キャッシュを作成"""
    # 現在時刻から1時間後に期限切れとなる認証情報を作成
    expiration = datetime.now(timezone.utc) + timedelta(hours=1)

    test_credentials = {
        "AccessKeyId": "TEST_ACCESS_KEY_ID",
        "SecretAccessKey": "TEST_SECRET_ACCESS_KEY",
        "SessionToken": "TEST_SESSION_TOKEN",
        "Expiration": expiration.isoformat(),
    }

    cache_path = Path(MFA_CREDENTIALS_CACHE)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    with open(cache_path, "w") as f:
        json.dump(test_credentials, f, indent=2)

    print(f"✅ テスト用キャッシュを作成しました: {cache_path}")
    print(f"   有効期限: {expiration.strftime('%Y-%m-%d %H:%M:%S %Z')}")


def create_expired_cache():
    """期限切れのテスト用認証情報キャッシュを作成"""
    # 現在時刻から1時間前に期限切れとなる認証情報を作成
    expiration = datetime.now(timezone.utc) - timedelta(hours=1)

    test_credentials = {
        "AccessKeyId": "EXPIRED_ACCESS_KEY_ID",
        "SecretAccessKey": "EXPIRED_SECRET_ACCESS_KEY",
        "SessionToken": "EXPIRED_SESSION_TOKEN",
        "Expiration": expiration.isoformat(),
    }

    cache_path = Path(MFA_CREDENTIALS_CACHE)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    with open(cache_path, "w") as f:
        json.dump(test_credentials, f, indent=2)

    print(f"⚠️ 期限切れのテスト用キャッシュを作成しました: {cache_path}")
    print(f"   有効期限: {expiration.strftime('%Y-%m-%d %H:%M:%S %Z')}")


def delete_cache():
    """キャッシュファイルを削除"""
    cache_path = Path(MFA_CREDENTIALS_CACHE)
    if cache_path.exists():
        cache_path.unlink()
        print(f"✅ キャッシュファイルを削除しました: {cache_path}")
    else:
        print(f"⚠️ キャッシュファイルが存在しません: {cache_path}")


def check_cache():
    """キャッシュファイルの内容を確認"""
    cache_path = Path(MFA_CREDENTIALS_CACHE)
    if not cache_path.exists():
        print(f"⚠️ キャッシュファイルが存在しません: {cache_path}")
        return

    with open(cache_path, "r") as f:
        credentials = json.load(f)

    expiration = datetime.fromisoformat(credentials["Expiration"])
    now = datetime.now(timezone.utc)
    time_remaining = (expiration - now).total_seconds()

    print(f"📄 キャッシュファイルの内容:")
    print(f"   ファイル: {cache_path}")
    print(f"   AccessKeyId: {credentials['AccessKeyId']}")
    print(f"   有効期限: {expiration.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"   残り時間: {time_remaining / 60:.1f}分")
    print(f"   状態: {'✅ 有効' if time_remaining > 300 else '❌ 期限切れまたは5分未満'}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python test_cache.py create    # 有効なテストキャッシュを作成")
        print("  python test_cache.py expired   # 期限切れのテストキャッシュを作成")
        print("  python test_cache.py check     # キャッシュの内容を確認")
        print("  python test_cache.py delete    # キャッシュを削除")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        create_test_cache()
    elif command == "expired":
        create_expired_cache()
    elif command == "check":
        check_cache()
    elif command == "delete":
        delete_cache()
    else:
        print(f"❌ 不明なコマンド: {command}")
        sys.exit(1)
