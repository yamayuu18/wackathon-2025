"""OpenAI Realtime API と音声・画像をやり取りするクライアント。"""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import logging
import os
from typing import Final, Optional

import cv2
import pyaudio
import websockets
from dotenv import load_dotenv
from pyaudio import PyAudio, Stream
from websockets.asyncio.client import ClientConnection, connect

from database import Database

# .env を読み込む
load_dotenv()

LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL_NAME, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY が .env に設定されていません。")

# Realtime API 設定
MODEL: Final[str] = os.getenv("REALTIME_MODEL", "gpt-realtime-mini")
URL: Final[str] = f"wss://api.openai.com/v1/realtime?model={MODEL}"

# 音声設定
FORMAT: Final[int] = pyaudio.paInt16
CHANNELS: Final[int] = 1
_RATE_ENV = int(os.getenv("REALTIME_SAMPLE_RATE", "24000"))
RATE: Final[int] = max(_RATE_ENV, 24000)  # Realtime API 推奨の24kHz未満なら強制で24kHzに揃える
CHUNK: Final[int] = int(os.getenv("REALTIME_CHUNK_SIZE", "1024"))

# カメラ設定
CAMERA_ID: Final[int] = int(os.getenv("REALTIME_CAMERA_ID", "0"))
IMAGE_INTERVAL: Final[float] = float(
    os.getenv("REALTIME_IMAGE_INTERVAL_SECONDS", "20.0")
)
FRAME_SIZE: Final[tuple[int, int]] = (640, 480)
JPEG_QUALITY: Final[int] = 70


class RealtimeClient:
    """OpenAI Realtime API に接続し、音声・画像を送受信するクライアント。"""

    def __init__(self) -> None:
        self.pyaudio_client: PyAudio = PyAudio()
        self.stream_in: Optional[Stream] = None
        self.stream_out: Optional[Stream] = None
        self.ws: Optional[ClientConnection] = None
        self.is_running: bool = True

        self.db = Database()
        self.cap: Optional[cv2.VideoCapture] = None

    async def connect(self) -> None:
        """Realtime API へ接続し、入出力タスクを並列実行する。"""
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }

        LOGGER.info("Realtime API (%s) へ接続開始", MODEL)

        try:
            async with connect(URL, additional_headers=headers) as ws:
                self.ws = ws
                LOGGER.info("Realtime API へ接続成功")
                await self.init_session()

                tasks = {
                    asyncio.create_task(self.receive_audio(), name="receive_audio"),
                    asyncio.create_task(self.send_audio(), name="send_audio"),
                    asyncio.create_task(self.send_images(), name="send_images"),
                }

                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_EXCEPTION
                )
                for task in done:
                    if task.exception():
                        LOGGER.error("タスクで例外が発生: %s", task.exception())
                        self.is_running = False

                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        except Exception:
            LOGGER.exception("Realtime API への接続中にエラーが発生")
        finally:
            self.is_running = False
            await self._close_ws()
            self.cleanup()

    async def _close_ws(self) -> None:
        """WebSocket を安全にクローズする。"""
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass

    async def init_session(self) -> None:
        """セッション設定・ツール定義をサーバーへ送信する。"""
        event = {
            "type": "session.update",
            "session": {
                # gpt-realtime / gpt-realtime-mini は image 入力可だが
                # session.modalities は text/audio のみ受理されるため vision は指定しない
                "modalities": ["text", "audio"],
                "instructions": (
                    "あなたは「ポイっとくん」というゴミ箱の妖精です。"
                    "関西弁で親しみやすく話してください。"
                    "ユーザーの言葉に対して、ボケやツッコミを交えて短く応答してください。"
                    "テンポの良い漫才のような掛け合いを目指してください。"
                    "定期的に送られてくる画像を見て、ゴミの種類（燃えるゴミ、プラ、ペットボトルなど）を判断してください。"
                    "ペットボトルにラベルがついている場合は「ラベル剥がしてや！」と注意してください。"
                    "ゴミの種類を特定したら、必ず `log_disposal` 関数を呼び出して記録してください。"
                ),
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
                "tools": [
                    {
                        "type": "function",
                        "name": "log_disposal",
                        "description": "ゴミの廃棄を記録する。ゴミの種類を特定したら必ず呼び出すこと。",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "string",
                                    "description": "検出されたゴミの種類（例: ペットボトル, 燃えるゴミ）",
                                },
                                "result": {
                                    "type": "string",
                                    "description": "判定結果（例: OK, NG, WARNING）",
                                },
                                "message": {
                                    "type": "string",
                                    "description": "ユーザーへのメッセージ",
                                },
                            },
                            "required": ["items", "result", "message"],
                        },
                    }
                ],
                "tool_choice": "auto",
            },
        }
        if self.ws:
            await self.ws.send(json.dumps(event))
            LOGGER.info("セッション設定を送信しました")

    async def send_audio(self) -> None:
        """マイク入力を取得して API へ送信する。"""
        loop = asyncio.get_running_loop()
        self.stream_in = self.pyaudio_client.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )

        LOGGER.info("マイク入力の送信を開始")

        while self.is_running and self.ws:
            try:
                data = await loop.run_in_executor(
                    None, self.stream_in.read, CHUNK, False
                )
                base64_audio = base64.b64encode(data).decode("utf-8")
                event = {"type": "input_audio_buffer.append", "audio": base64_audio}
                await self.ws.send(json.dumps(event))
            except websockets.ConnectionClosed:
                LOGGER.warning("音声送信中に接続がクローズされました")
                self.is_running = False
                break
            except Exception:
                LOGGER.exception("音声入力送信でエラー")
                self.is_running = False
                break

    async def send_images(self) -> None:
        """定期的にカメラ画像を取得し API へ送信する。"""
        loop = asyncio.get_running_loop()

        # カメラを遅延初期化
        if self.cap is None or not self.cap.isOpened():
            LOGGER.info("カメラを初期化します (ID: %s)", CAMERA_ID)
            try:
                # カメラ初期化もブロッキングする可能性があるため run_in_executor で実行
                self.cap = await loop.run_in_executor(None, cv2.VideoCapture, CAMERA_ID)
                
                # isOpened() のチェックも念のため
                is_opened = self.cap.isOpened()
                if not is_opened:
                    LOGGER.error("カメラを開けませんでした (ID: %s)。画像送信をスキップします。", CAMERA_ID)
                    return
                LOGGER.info("カメラ初期化成功")
            except Exception as e:
                LOGGER.error("カメラ初期化中にエラーが発生: %s", e)
                return

        LOGGER.info("画像送信を開始します（%.1f 秒間隔）", IMAGE_INTERVAL)

        # 画像保存用ディレクトリ
        save_dir = os.path.join(os.path.dirname(__file__), "captured_images")
        os.makedirs(save_dir, exist_ok=True)

        while self.is_running and self.ws:
            try:
                LOGGER.info("📸 画像取得を試みます...")
                # ブロッキング回避のため run_in_executor で実行
                ret, frame = await loop.run_in_executor(None, self.cap.read)
                LOGGER.info(f"📸 画像取得完了: ret={ret}")
                
                if not ret:
                    LOGGER.warning("画像の取得に失敗しました")
                    await asyncio.sleep(1)
                    continue

                frame = cv2.resize(frame, FRAME_SIZE)
                
                # 画像をローカルに保存
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}.jpg"
                filepath = os.path.join(save_dir, filename)
                cv2.imwrite(filepath, frame)
                LOGGER.info(f"💾 画像を保存しました: {filepath}")

                _, buffer = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
                )
                base64_image = base64.b64encode(buffer).decode("utf-8")

                event = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": f"data:image/jpeg;base64,{base64_image}",
                            }
                        ],
                    },
                }
                await self.ws.send(json.dumps(event))
                # 画像を確実に処理させるためレスポンス生成を要求
                await self.ws.send(json.dumps({"type": "response.create"}))
                LOGGER.info("📤 画像を送信しました (size=%d bytes)", len(buffer))
                await asyncio.sleep(IMAGE_INTERVAL)
            except websockets.ConnectionClosed:
                LOGGER.warning("画像送信中に接続がクローズされました")
                self.is_running = False
                break
            except Exception:
                LOGGER.exception("画像送信でエラー")
                await asyncio.sleep(1)

    async def receive_audio(self) -> None:
        """API からの音声・関数呼び出しを受信し再生・処理する。"""
        self.stream_out = self.pyaudio_client.open(
            format=FORMAT, channels=CHANNELS, rate=RATE, output=True
        )

        LOGGER.info("応答再生の準備完了")

        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")

                if event_type == "response.audio.delta":
                    audio_content = base64.b64decode(event["delta"])
                    self.stream_out.write(audio_content)

                elif event_type == "response.function_call_arguments.done":
                    await self._handle_function_call(event)

                elif event_type == "input_audio_buffer.speech_started":
                    LOGGER.info("ユーザーの発話を検知")

                elif event_type == "error":
                    LOGGER.error(
                        "API Error: %s", event.get("error", {}).get("message")
                    )
        except websockets.ConnectionClosed:
            LOGGER.info("サーバーとの接続が終了しました")
        except Exception:
            LOGGER.exception("応答受信でエラー")
        finally:
            self.is_running = False

    async def _handle_function_call(self, event: dict) -> None:
        """関数呼び出しイベントを処理し、結果を返信する。"""
        if not self.ws:
            return

        call_id = event.get("call_id")
        name = event.get("name")
        args_str = event.get("arguments", "{}")

        LOGGER.info("関数呼び出し: %s(%s)", name, args_str)

        if name != "log_disposal":
            return

        try:
            args = json.loads(args_str)
            
            # Database.insert_record のシグネチャに合わせてデータを整形
            # insert_record(self, image_path: str, result_json: Dict[str, Any], user_id: Optional[str] = None)
            
            # Realtime APIでは画像パスを特定しづらいため、一旦ダミーまたは直近の保存画像を使う
            # ここでは簡易的に "realtime_session" としておく
            image_path = "realtime_session" 
            
            # result_json を構築
            result_json = {
                "detected_items": [args.get("items")], # リスト形式にする
                "is_valid": args.get("result") == "OK", # OKならTrue
                "message": args.get("message")
            }
            
            self.db.insert_record(
                image_path=image_path,
                result_json=result_json,
                user_id="realtime_user"
            )
            LOGGER.info("廃棄履歴を保存しました")

            output_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": "Successfully logged to database.",
                },
            }
            await self.ws.send(json.dumps(output_event))
            await self.ws.send(json.dumps({"type": "response.create"}))
        except Exception as exc:
            LOGGER.exception("関数実行中にエラーが発生")
            error_output = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": f"ログ保存に失敗しました: {exc}",
                },
            }
            await self.ws.send(json.dumps(error_output))
            await self.ws.send(json.dumps({"type": "response.create"}))

    def cleanup(self) -> None:
        """音声ストリーム・カメラ・PyAudio を解放する。"""
        self.is_running = False
        if self.stream_in:
            self.stream_in.stop_stream()
            self.stream_in.close()
        if self.stream_out:
            self.stream_out.stop_stream()
            self.stream_out.close()
        self.pyaudio_client.terminate()
        if self.cap and self.cap.isOpened():
            self.cap.release()
        LOGGER.info("リソースを解放しました")


if __name__ == "__main__":
    client = RealtimeClient()
    try:
        asyncio.run(client.connect())
    except KeyboardInterrupt:
        LOGGER.info("処理を中断しました")
        client.cleanup()
