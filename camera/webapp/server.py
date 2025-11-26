import asyncio
import base64
import datetime
import json
import logging
import os
import sys
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from websockets.asyncio.client import connect

# 親ディレクトリのモジュールをインポートできるようにパスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Database

# .env を読み込む
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOGGER = logging.getLogger("webapp")

app = FastAPI()

# 静的ファイルの提供 (index.htmlなど)
static_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# OpenAI Realtime API 設定
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("REALTIME_MODEL", "gpt-realtime-mini")
URL = f"wss://api.openai.com/v1/realtime?model={MODEL}"

# データベース
db = Database()

@app.get("/")
async def get():
    with open(os.path.join(static_dir, "index.html")) as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("クライアント接続: %s", websocket.client)

    openai_ws = None
    
    try:
        # OpenAI Realtime API へ接続
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }
        
        async with connect(URL, additional_headers=headers) as openai_ws:
            LOGGER.info("OpenAI Realtime API へ接続成功")
            
            # セッション初期化
            await init_session(openai_ws)
            
            # 双方向リレー
            async def client_to_openai():
                try:
                    while True:
                        data = await websocket.receive_text()
                        event = json.loads(data)
                        
                        # クライアントからのイベントを処理
                        if event.get("type") == "input_audio_buffer.append":
                            # 音声データはそのまま転送
                            await openai_ws.send(json.dumps(event))
                        
                        elif event.get("type") == "conversation.item.create":
                            # 画像データを保存
                            try:
                                content = event.get("item", {}).get("content", [])
                                for item in content:
                                    if item.get("type") == "input_image":
                                        image_url = item.get("image_url", "")
                                        if image_url.startswith("data:image/jpeg;base64,"):
                                            base64_data = image_url.split(",")[1]
                                            image_data = base64.b64decode(base64_data)
                                            
                                            # 保存ディレクトリ
                                            save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captured_images")
                                            os.makedirs(save_dir, exist_ok=True)
                                            
                                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                            filename = f"{timestamp}.jpg"
                                            filepath = os.path.join(save_dir, filename)
                                            
                                            with open(filepath, "wb") as f:
                                                f.write(image_data)
                                            LOGGER.info(f"💾 画像を保存しました: {filepath}")
                            except Exception as e:
                                LOGGER.error(f"画像保存エラー: {e}")

                            # OpenAIへ転送
                            await openai_ws.send(json.dumps(event))
                            
                        elif event.get("type") == "response.create":
                            await openai_ws.send(json.dumps(event))
                            
                except WebSocketDisconnect:
                    LOGGER.info("クライアント切断")
                except Exception as e:
                    LOGGER.error("Client -> OpenAI エラー: %s", e)

            async def openai_to_client():
                try:
                    async for message in openai_ws:
                        event = json.loads(message)
                        event_type = event.get("type")
                        
                        if event_type == "response.function_call_arguments.done":
                            await handle_function_call(event, openai_ws)
                        
                        # クライアントへ転送
                        await websocket.send_text(message)
                        
                except Exception as e:
                    LOGGER.error("OpenAI -> Client エラー: %s", e)

            # 並列実行
            await asyncio.gather(client_to_openai(), openai_to_client())

    except Exception as e:
        LOGGER.error("WebSocket エラー: %s", e)
    finally:
        if openai_ws:
            await openai_ws.close()
        LOGGER.info("接続終了")

async def init_session(ws):
    """セッション設定を送信"""
    event = {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": (
                "あなたは「ポイっとくん」というゴミ箱の妖精ですが、**ペットボトル専用**の厳しい検査官でもあります。"
                "関西弁で親しみやすく話してください。"
                "定期的に送られてくる画像を見て、以下の基準で厳しく判定してください。"
                "**判定は内部でステップバイステップで行い、その過程は口に出さないでください。**"
                "**「記録します」などのシステム的な発言もしないでください。**"
                "ユーザーには、判定結果（OK/NG）と、NGの場合はその理由（「キャップ外して！」など）だけを短く関西弁で怒って伝えてください。"
                "1. **ペットボトル以外**（缶、ビン、燃えるゴミなど）は全てNGです。"
                "2. **キャップ**がついているかよく見てください。ついている場合はNGです。"
                "3. **ラベル**がついているかよく見てください。透明なボトルにラベルが残っている場合はNGです。"
                "4. 中身が残っている場合もNGです。"
                "5. 上記の違反がなく、綺麗なペットボトルのみOKとして関西弁で褒めて伝えてください。"
                "ゴミの種類を特定したら、必ず `log_disposal` 関数を呼び出して記録してください。"
                "記録時の `result` は、OKの場合のみ 'OK'、それ以外は 'NG' としてください。"
                "NGの場合は、`rejection_reason` に理由（例: wrong_item, has_cap, has_label, dirty）を記録してください。"
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
                                "description": "検出されたゴミの種類（例: ペットボトル, 缶）",
                            },
                            "result": {
                                "type": "string",
                                "description": "判定結果（OK: 許可, NG: 拒否）。",
                            },
                            "rejection_reason": {
                                "type": "string",
                                "description": "NGの理由（wrong_item: ペットボトル以外, has_cap: キャップあり, has_label: ラベルあり, dirty: 汚れ・中身あり）。OKの場合はnull。",
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
    await ws.send(json.dumps(event))
    LOGGER.info("セッション設定送信完了")

async def handle_function_call(event, ws):
    """Function Calling の処理"""
    call_id = event.get("call_id")
    name = event.get("name")
    args_str = event.get("arguments", "{}")
    
    LOGGER.info("関数呼び出し: %s(%s)", name, args_str)
    
    if name == "log_disposal":
        try:
            args = json.loads(args_str)
            
            # DB保存
            image_path = "webapp_session" 
            
            result_json = {
                "detected_items": [args.get("items")],
                "is_valid": args.get("result") == "OK",
                "rejection_reason": args.get("rejection_reason"),
                "message": args.get("message")
            }
            
            db.insert_record(
                image_path=image_path,
                result_json=result_json,
                user_id="webapp_user",
                rejection_reason=args.get("rejection_reason")
            )
            LOGGER.info("DB保存完了")
            
            output_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": "Successfully logged to database.",
                },
            }
            await ws.send(json.dumps(output_event))
            
        except Exception as e:
            LOGGER.error("関数実行エラー: %s", e)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
