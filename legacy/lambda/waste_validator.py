"""
ゴミ分別判定Lambda関数

S3イベントをトリガーにして画像を取得し、
OpenAI API (GPT-4o-mini) で画像認識を行い、
正しいゴミ分別かどうかを判定して音声メッセージを生成します。
"""

import json
import traceback
from datetime import datetime
from typing import Any, Optional
from urllib.parse import unquote_plus

import boto3

from openai_utils import OpenAIClient
from polly_config import (
    OUTPUT_FORMAT,
    VOICE_BUCKET_NAME,
    VOICE_FILE_EXTENSION,
    VOICE_FILE_PREFIX,
)

# AWS クライアントの初期化 (S3のみ使用)
s3 = boto3.client("s3")

# OpenAI クライアントの初期化
openai_client = OpenAIClient()


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda関数のエントリーポイント

    Parameters:
        event: S3イベント情報を含む辞書
        context: Lambda実行コンテキスト

    Returns:
        判定結果と音声メッセージを含む辞書
    """
    print(f"[INFO] Lambda 関数開始")
    print(f"[DEBUG] Event: {json.dumps(event, ensure_ascii=False)}")

    try:
        # S3イベントからバケット名とオブジェクトキーを取得
        if "Records" not in event:
            print("[ERROR] S3イベントにRecordsが含まれていません")
            return create_response(
                is_valid=False,
                message="イベント形式が不正です。",
                detected_items=[],
                error="No Records in event",
            )

        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])

        print(f"[INFO] S3イベント受信: {bucket}/{key}")

        # S3から画像データを取得
        print(f"[INFO] S3から画像を取得中...")
        s3_response = s3.get_object(Bucket=bucket, Key=key)
        image_bytes = s3_response["Body"].read()

        # OpenAIで画像を解析
        print(f"[INFO] OpenAI Vision API を呼び出し中...")
        analysis_result = openai_client.analyze_image(image_bytes)
        print(f"[INFO] 解析完了: {json.dumps(analysis_result, ensure_ascii=False)}")

        # エラーチェック
        if "error" in analysis_result:
            return create_response(
                is_valid=False,
                message=analysis_result.get("message", "エラーが発生しました"),
                detected_items=[],
                error=analysis_result.get("error"),
            )

        # 結果の構築
        return create_response(
            is_valid=analysis_result.get("is_valid", False),
            message=analysis_result.get("message", ""),
            detected_items=analysis_result.get("detected_items", []),
            categories=analysis_result.get("categories", []),
            prohibited_items=analysis_result.get("prohibited_items", []),
            label_removed=analysis_result.get("label_removed", False),
            is_full=analysis_result.get("is_full", False),
        )

    except Exception as e:
        error_msg = f"予期しないエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        return create_response(
            is_valid=False,
            message="システムエラーが発生しました。管理者に連絡してください。",
            detected_items=[],
            error=error_msg,
            skip_audio=True,  # エラー時は音声生成をスキップ
        )


def generate_audio_with_openai(message: str) -> Optional[str]:
    """
    OpenAI TTSで音声を生成しS3に保存（バックアップ用）

    Parameters:
        message: 音声化するテキストメッセージ

    Returns:
        音声ファイルのS3 URL、失敗時はNone
    """
    try:
        print(f"[INFO] OpenAI音声合成開始: {message}")

        # 音声合成
        audio_data = openai_client.generate_speech(message)
        
        if not audio_data:
            print("[ERROR] 音声データの生成に失敗しました")
            return None

        print(f"[INFO] 音声合成完了: {len(audio_data)} bytes")

        # S3に保存するファイル名を生成
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        audio_key = f"{VOICE_FILE_PREFIX}{timestamp}{VOICE_FILE_EXTENSION}"

        # S3に音声ファイルをアップロード
        print(f"[INFO] S3アップロード開始: {VOICE_BUCKET_NAME}/{audio_key}")
        s3.put_object(
            Bucket=VOICE_BUCKET_NAME,
            Key=audio_key,
            Body=audio_data,
            ContentType=f"audio/{OUTPUT_FORMAT}",
        )

        # S3 URLを生成
        audio_url = f"https://{VOICE_BUCKET_NAME}.s3.ap-northeast-1.amazonaws.com/{audio_key}"
        print(f"[INFO] 音声URL生成完了: {audio_url}")

        return audio_url

    except Exception as e:
        error_msg = f"音声生成・アップロードエラー: {str(e)}"
        print(f"[ERROR] {error_msg}")
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        return None


def save_result_to_s3(result_data: dict[str, Any]) -> Optional[str]:
    """
    解析結果をJSONとしてS3に保存（ローカルのVoicevox連携用）

    Parameters:
        result_data: 保存するデータ

    Returns:
        保存したS3キー、失敗時はNone
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # images/xxx.jpg -> results/xxx.json のように対応付けるのが理想だが
        # ここではシンプルにタイムスタンプで保存
        json_key = f"results/result_{timestamp}.json"

        print(f"[INFO] 解析結果をS3に保存: {VOICE_BUCKET_NAME}/{json_key}")
        s3.put_object(
            Bucket=VOICE_BUCKET_NAME,
            Key=json_key,
            Body=json.dumps(result_data, ensure_ascii=False),
            ContentType="application/json",
        )
        return json_key

    except Exception as e:
        print(f"[ERROR] S3への結果保存失敗: {str(e)}")
        print(f"[ERROR] Traceback:\n{traceback.format_exc()}")
        return None


def create_response(
    is_valid: bool,
    message: str,
    detected_items: list[str],
    categories: Optional[list[str]] = None,
    prohibited_items: Optional[list[str]] = None,
    label_removed: bool = False,
    is_full: bool = False,
    error: Optional[str] = None,
    skip_audio: bool = False,
) -> dict[str, Any]:
    """
    Lambda関数のレスポンスを生成し、結果をS3に保存
    """
    import os
    
    # OpenAI TTSを使用するかどうか（環境変数で制御）
    enable_openai_tts = os.environ.get("ENABLE_OPENAI_TTS", "false").lower() == "true"
    audio_url = None

    if enable_openai_tts and not skip_audio:
        audio_url = generate_audio_with_openai(message)

    response_body = {
        "is_valid": is_valid,
        "message": message,
        "detected_items": detected_items,
        "categories": categories or [],
        "prohibited_items": prohibited_items or [],
        "label_removed": label_removed,
        "is_full": is_full,
        "timestamp": datetime.now().isoformat(),
    }

    if audio_url:
        response_body["audio_url"] = audio_url

    if error:
        response_body["error"] = error

    # Voicevox連携のためにS3にJSONを保存
    # エラー時でもメッセージを表示するために保存する
    save_result_to_s3(response_body)

    return {
        "statusCode": 200,
        "body": json.dumps(response_body, ensure_ascii=False),
    }
