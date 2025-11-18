"""
AWS Polly音声合成設定モジュール

音声生成に使用するPollyの設定値を定義します。
"""

import os
from typing import Final

# AWS Polly設定
VOICE_ENGINE: Final[str] = "neural"  # 音声エンジン（neural: 高品質、standard: 標準）
VOICE_ID: Final[str] = "Takumi"  # 音声ID（日本語男性）
VOICE_LANGUAGE: Final[str] = "ja-JP"  # 言語コード
OUTPUT_FORMAT: Final[str] = "mp3"  # 音声フォーマット（mp3, ogg_vorbis, pcm）
SAMPLE_RATE: Final[str] = "24000"  # サンプリングレート（24000Hz推奨）

# S3音声バケット設定
VOICE_BUCKET_NAME: Final[str] = os.getenv(
    "VOICE_BUCKET_NAME", "wackathon-2025-voice-responses"
)

# 音声ファイル設定
VOICE_FILE_PREFIX: Final[str] = "voice_response_"  # ファイル名プレフィックス
VOICE_FILE_EXTENSION: Final[str] = ".mp3"  # ファイル拡張子

# Polly Neural音声の利用可能な日本語音声ID
# Takumi: 男性、落ち着いた声
# Kazuha: 女性、明るい声
# Tomoko: 女性、優しい声
AVAILABLE_VOICES: Final[list[str]] = ["Takumi", "Kazuha", "Tomoko"]
