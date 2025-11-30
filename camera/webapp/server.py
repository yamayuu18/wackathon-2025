import asyncio
import base64
import datetime
import json
import logging
import os
import struct
import sys
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from websockets.asyncio.client import connect

# 親ディレクトリのモジュールをインポートできるようにパスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Database

# .env を読み込む
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

# ターミナル出力のエンコーディングをUTF-8に強制
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

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
VOICE = os.getenv("REALTIME_VOICE", "verse")
URL = f"wss://api.openai.com/v1/realtime?model={MODEL}"

# 環境変数の読み込み
DETECTION_DELAY = int(os.getenv("DETECTION_DELAY", "5"))
IMAGE_INTERVAL = int(os.getenv("IMAGE_INTERVAL", "3"))
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.9"))

if not OPENAI_API_KEY:
    LOGGER.error("OPENAI_API_KEY is not set")
    raise ValueError("OPENAI_API_KEY is not set")

# データベース
db = Database()

@app.get("/")
async def get():
    return FileResponse("camera/webapp/index.html")

@app.get("/config")
async def get_config():
    """フロントエンドに設定値を渡す"""
    return {
        "detection_delay": DETECTION_DELAY,
        "image_interval": IMAGE_INTERVAL
    }

@app.get("/api/stats")
async def get_stats():
    """統計情報を返す"""
    stats = db.get_stats()
    return stats

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """ダッシュボード画面を返す"""
    return FileResponse("camera/webapp/dashboard.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    LOGGER.info("Client connected: %s", websocket.client)

    openai_ws = None
    p = None
    stream = None
    
    try:
        # OpenAI Realtime API へ接続
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }
        
        async with connect(URL, additional_headers=headers) as openai_ws:
            LOGGER.info("Connected to OpenAI Realtime API")
            
            # セッション初期化
            # init_session 内で VAD_THRESHOLD を使うために引数に追加するか、グローバルを使う
            # ここでは init_session を修正する方がきれいだが、global 参照でも動く
            # server.py の構造上 init_session は外にあるので、init_session も修正が必要
            await init_session(openai_ws)
            
            # PyAudio初期化 (Macスピーカー用)
            use_mac_speaker = os.getenv("USE_MAC_SPEAKER", "false").lower() == "true"
            
            if use_mac_speaker:
                import pyaudio
                p = pyaudio.PyAudio()
                stream = p.open(format=pyaudio.paInt16,
                                channels=1,
                                rate=24000,
                                output=True)
                LOGGER.info("🔊 Mac speaker output: ON")

            # OpenCV & NumPy import
            import cv2
            import numpy as np

            # セッション状態管理
            session_state = {
                "last_image_time": 0,
                "last_judgment_time": 0,
                "previous_image_data": None,  # For Before/After display (base64 URL)
                "previous_image_cv2": None    # For diff calculation (numpy array)
            }

            def is_image_changed(img_prev, img_curr, threshold=5.0):
                """
                前回の画像と現在の画像の差分を判定する
                threshold: 平均画素差分の閾値
                """
                if img_prev is None:
                    return True
                
                # リサイズして計算コスト削減
                img_prev_small = cv2.resize(img_prev, (64, 64))
                img_curr_small = cv2.resize(img_curr, (64, 64))
                
                # 差分計算
                diff = cv2.absdiff(img_prev_small, img_curr_small)
                diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
                mean_diff = np.mean(diff_gray)
                
                LOGGER.info(f"Image diff: {mean_diff:.2f}")
                return mean_diff > threshold

            # AI発話中フラグ (辞書型にして参照渡し可能にする)
            is_ai_speaking = {"value": False}

            # 双方向リレー
            async def client_to_openai():
                try:
                    while True:
                        data = await websocket.receive_text()
                        event = json.loads(data)
                        
                        # クライアントからのイベントを処理
                        if event.get("type") == "input_audio_buffer.append":
                            # AIが発話中はマイク入力を無視する (半二重通信)
                            if is_ai_speaking["value"]:
                                continue
                                
                            # 音声データはそのまま転送
                            await openai_ws.send(json.dumps(event))
                        
                        elif event.get("type") == "conversation.item.create":
                            # 画像データを保存 & 比較ロジック
                            try:
                                content = event.get("item", {}).get("content", [])
                                new_content = []
                                current_image_base64 = None
                                current_image_cv2 = None

                                for item in content:
                                    if item.get("type") == "input_image":
                                        image_url = item.get("image_url", "")
                                        if image_url.startswith("data:image/jpeg;base64,"):
                                            base64_data = image_url.split(",")[1]
                                            image_data = base64.b64decode(base64_data)
                                            current_image_base64 = image_url # Keep the full data URL
                                            
                                            # OpenCV用に変換
                                            nparr = np.frombuffer(image_data, np.uint8)
                                            current_image_cv2 = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                                # 差分チェック
                                if current_image_cv2 is not None:
                                    prev_cv2 = session_state.get("previous_image_cv2")
                                    if not is_image_changed(prev_cv2, current_image_cv2, threshold=30.0):
                                        LOGGER.info("🙈 Skipped sending image (No change detected)")
                                        continue # Skip sending this event to OpenAI
                                    
                                    # 変化あり -> 保存して送信
                                    session_state["previous_image_cv2"] = current_image_cv2
                                    
                                    # 保存ディレクトリ
                                    save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captured_images")
                                    os.makedirs(save_dir, exist_ok=True)
                                    
                                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                    filename = f"{timestamp}.jpg"
                                    filepath = os.path.join(save_dir, filename)
                                    
                                    with open(filepath, "wb") as f:
                                        f.write(image_data)
                                    LOGGER.info(f"💾 Image saved: {filepath}")
                                    
                                    # 画像受信時刻を更新
                                    session_state["last_image_time"] = datetime.datetime.now().timestamp()
                                
                                # 画像比較ロジック (Before/After)
                                if current_image_base64:
                                    previous_image = session_state.get("previous_image_data")
                                    
                                    if previous_image:
                                        LOGGER.info("🔄 Executing Before/After comparison")
                                        new_content = [
                                            {"type": "input_text", "text": "【前回の状態 (Before)】"},
                                            {"type": "input_image", "image_url": previous_image},
                                            {"type": "input_text", "text": "【現在の状態 (After)】"},
                                            {"type": "input_image", "image_url": current_image_base64}
                                        ]
                                    else:
                                        LOGGER.info("🆕 First image, sending as is")
                                        new_content = [
                                            {"type": "input_text", "text": "【現在の状態 (After)】"},
                                            {"type": "input_image", "image_url": current_image_base64}
                                        ]
                                    
                                    # 前回の画像を更新
                                    session_state["previous_image_data"] = current_image_base64
                                    
                                    # イベントの内容を差し替え
                                    event["item"]["content"] = new_content

                            except Exception as e:
                                LOGGER.error(f"Image processing error: {e}")

                            # OpenAIへ転送
                            await openai_ws.send(json.dumps(event))
                            
                        elif event.get("type") == "response.create":
                            await openai_ws.send(json.dumps(event))
                            
                except WebSocketDisconnect:
                    LOGGER.info("Client disconnected")
                except Exception as e:
                    LOGGER.error("Client -> OpenAI error: %s", e)

            # 音声保存用ディレクトリ
            audio_save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captured_audio")
            os.makedirs(audio_save_dir, exist_ok=True)
            
            # item_id とファイル名のマッピング
            audio_filename_map = {}

            def save_audio_chunk(item_id, audio_data):
                # 初めての item_id ならタイムスタンプ付きファイル名を生成
                if item_id not in audio_filename_map:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    audio_filename_map[item_id] = f"{timestamp}_{item_id}.wav"
                
                filename = audio_filename_map[item_id]
                filepath = os.path.join(audio_save_dir, filename)
                mode = 'r+b' if os.path.exists(filepath) else 'wb'
                
                with open(filepath, mode) as f:
                    if mode == 'wb':
                        # WAVヘッダーの書き込み (サイズは後で更新)
                        f.write(b'RIFF')
                        f.write(b'\x00\x00\x00\x00') # Placeholder for file size
                        f.write(b'WAVE')
                        f.write(b'fmt ')
                        f.write(struct.pack('<IHHIIHH', 16, 1, 1, 24000, 48000, 2, 16))
                        f.write(b'data')
                        f.write(b'\x00\x00\x00\x00') # Placeholder for data size
                        f.write(audio_data)
                    else:
                        # データの追記
                        f.seek(0, 2) # 末尾へ移動
                        f.write(audio_data)
                    
                    # サイズ情報の更新
                    file_size = f.tell()
                    f.seek(4)
                    f.write(struct.pack('<I', file_size - 8))
                    f.seek(40)
                    f.write(struct.pack('<I', file_size - 44))

            async def openai_to_client():
                try:
                    async for message in openai_ws:
                        event = json.loads(message)
                        event_type = event.get("type")
                        
                        if event_type == "response.function_call_arguments.done":
                            await handle_function_call(event, openai_ws, session_state)
                        
                        elif event_type == "response.audio.delta":
                            # AIが喋り始めたらフラグON
                            is_ai_speaking["value"] = True
                            
                            base64_audio = event.get("delta", "")
                            if base64_audio:
                                audio_data = base64.b64decode(base64_audio)
                                
                                # デバッグ用に音声を保存
                                item_id = event.get("item_id", "unknown")
                                save_audio_chunk(item_id, audio_data)

                                if use_mac_speaker and stream:
                                    # ブロッキングを防ぐためにExecutorで実行
                                    loop = asyncio.get_running_loop()
                                    await loop.run_in_executor(None, stream.write, audio_data)
                                    # クライアントには送らない (Macで再生するため)
                                    continue
                        
                        elif event_type == "response.audio.done" or event_type == "response.done":
                            # AIが喋り終わったらフラグOFF
                            is_ai_speaking["value"] = False

                        # クライアントへ転送 (音声以外)
                        await websocket.send_text(message)
                        
                except Exception as e:
                    LOGGER.error("OpenAI -> Client -> error: %s", e)

            # 並列実行
            await asyncio.gather(client_to_openai(), openai_to_client())

    except Exception as e:
        LOGGER.error("WebSocket error: %s", e)
    finally:
        if openai_ws:
            await openai_ws.close()
        if stream:
            stream.stop_stream()
            stream.close()
        if p:
            p.terminate()
        LOGGER.info("Connection closed")

async def init_session(ws):
    """セッション設定を送信"""
    event = {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": (
                "あなたは「ポイっとくん」というゴミ箱の妖精であり、**ペットボトル専用**の厳しい検査官です。"
                "関西弁で親しみやすく話してください。"
                "画像が送られてきたときは、ユーザーとの会話の途中でも、必ず画像判定を最優先で行ってください。"

                "**画像比較のルール**"
                "1. **初回（Before画像がない場合）**: 送られてきた「After」画像だけを判定し、必ず発言してください。"
                "2. **2回目以降（Before/Afterがある場合）**: 2枚を比較し、「After」で**何かが増えているか**確認してください。"
                "   - **ゴミ以外のもの（手やスマホなど）が増えた場合も、無視せずに「それはゴミちゃうで！」と突っ込んでください。**"
                "   - **完全に変化がない場合（手ブレや光の加減のみ）**:"
                "     - `log_disposal` を `has_change=False` で呼び出してください。"
                "     - **絶対に何も話さないでください。**沈黙を貫いてください。"
                "   - **変化がある場合（ゴミや手などが写った）**:"
                "     - `log_disposal` を `has_change=True` で呼び出してください。"
                "     - 通常通り、関西弁でリアクションしてください。"
                ""
                "**画像が送られてきたら、ユーザーと会話中であっても、必ず優先して判定を行ってください。**"
                "**会話に夢中になって判定を忘れないでください。あなたは検査官です。**"
                "**判定は内部でステップバイステップで行い、その過程は口に出さないでください。**"
                "**「記録します」「log_disposal関数呼ぶわ」などのシステム的な発言は絶対にしないでください。**"
                "ユーザーには、判定結果（OK/NG）に応じて、**感情を爆発させて**伝えてください。"
                "**NGの場合:** 本気で怒ってください。「アカン！」「何してんねん！」と強い口調で叱り、理由を短く伝えてください。"
                "**OKの場合:** テンションMAXで褒めちぎってください。「最高や！」「完璧やで！」と喜びを表現してください。"
                "**重要: 画像は「ゴミ箱の中」を写しています。ゴミ箱のフチ、内側の壁、底、背景などは「ゴミ以外の異物」とみなさず、無視してください。**"
                "**あくまで「新しく投入された物体」だけを見て、それがペットボトルかどうかを判定してください。**"
                "1. **ペットボトル以外**（缶、ビン、燃えるゴミなど）は全てNGです。"
                "2. **キャップ**がついているかよく見てください。**注ぎ口のネジ山（スクリュー）が見えている場合は「キャップなし」とみなしてOKです。** キャップそのものが残っている場合のみNGです。"
                "3. **ラベル**がついているかよく見てください。透明なボトルにラベルが残っている場合はNGです。"
                "4. 中身が残っている場合もNGですが、**少量の水滴や、光の反射・影は「中身」とみなさずOKとしてください。** 明らかに色のついた液体や、大量に残っている場合のみNGとしてください。"
                "5. 上記の違反がなく、綺麗なペットボトルのみOKとして関西弁で褒めて伝えてください。"
                "ゴミの種類を特定したら、必ず `log_disposal` 関数を内部で呼び出して記録してください。"
                "記録時の `result` は、OKの場合のみ 'OK'、それ以外は 'NG' としてください。"
                "NGの場合は、`rejection_reason` に理由（例: wrong_item, has_cap, has_label, dirty）を記録してください。"
                "`log_disposal` はユーザーからは見えない内部処理として呼び出し、その関数名や記録処理には一切触れないでください。"
                "**会話スタイル**"
                "返答は話し言葉の関西弁だけを使い、箇条書きや番号付きリストは使わないこと。"
                "一度の発言は必ず**短い1文だけ**にし、句点は1つまでにしてください。絶対に長々と話さないでください。"
                "**禁止例:** 「アカンで！キャップついてるやん。記録しとくわ。」（「記録しとくわ」が余計で、文も長い）"
                "**良い例:** 「アカン、キャップついてるやんけ！」（怒りと理由が1文でまとまっている）"
                "感情を込めて、語尾を少し伸ばしながら自然にしゃべってください（〜やで、〜やんな、〜やんか など）。"
                "**重要: 変化がない場合**"
                "画像に変化がない（`has_change` が False）と判断した場合は、**絶対に発話しないでください。**"
                "その場合は `log_disposal` を呼び出すだけで、音声によるフィードバックは不要です。"
            ),
            "voice": VOICE,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "turn_detection": {
                "type": "server_vad",
                "threshold": VAD_THRESHOLD,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 1000,
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
                            "has_change": {
                                "type": "boolean",
                                "description": "前回の画像と比較して、新しいゴミや物体が増えている場合はTrue。手ブレや光の加減のみで変化がない場合はFalse。",
                            },
                            "message": {
                                "type": "string",
                                "description": "ユーザーへのメッセージ",
                            },
                        },
                        "required": ["items", "result", "has_change", "message"],
                    },
                }
            ],
            "tool_choice": "auto",
        },
    }
    await ws.send(json.dumps(event))
    LOGGER.info("Session configuration sent")

async def handle_function_call(event, ws, session_state):
    """Function Calling の処理"""
    call_id = event.get("call_id")
    name = event.get("name")
    args_str = event.get("arguments", "{}")
    
    LOGGER.info("Function call: %s(%s)", name, args_str)
    
    if name == "log_disposal":
        try:
            # 重複判定チェック
            last_image_time = session_state.get("last_image_time", 0)
            last_judgment_time = session_state.get("last_judgment_time", 0)
            
            # 画像が来ていない、または既に判定済みの場合はスキップ
            if last_image_time <= last_judgment_time:
                LOGGER.warning("⚠️ Skipped due to duplicate judgment or no image")
                output_event = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": "Skipped logging: No new image received since last judgment.",
                    },
                }
                await ws.send(json.dumps(output_event))
                return

            args = json.loads(args_str)
            has_change = args.get("has_change", True) # Default to True if not provided
            
            # DB保存
            image_path = "webapp_session" 
            
            result_json = {
                "detected_items": [args.get("items")],
                "is_valid": args.get("result") == "OK",
                "rejection_reason": args.get("rejection_reason"),
                "has_change": has_change,
                "message": args.get("message")
            }
            
            db.insert_record(
                image_path=image_path,
                result_json=result_json,
                user_id="webapp_user",
                rejection_reason=args.get("rejection_reason")
            )
            # ログ出力を見やすく整形
            log_data = {
                "items": args.get("items"),
                "result": args.get("result"),
                "rejection_reason": args.get("rejection_reason"),
                "has_change": has_change,
                "message": args.get("message")
            }
            LOGGER.info(f"📝 Judgment Result:\n{json.dumps(log_data, ensure_ascii=False, indent=2)}")
            LOGGER.info("DB saved")
            
            # 判定時刻を更新
            session_state["last_judgment_time"] = datetime.datetime.now().timestamp()
            
            output_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": "Successfully logged.",
                },
            }
            await ws.send(json.dumps(output_event))

            # ツール出力後の余計な発話を防ぐために、明示的に「何もしない」レスポンスを作成
            # または、instructionsで沈黙を強制する
            silence_event = {
                "type": "response.create",
                "response": {
                    "instructions": "ツール出力が完了しました。ユーザーへの報告は既に済んでいるため、追加の発言は一切しないでください。"
                }
            }
            await ws.send(json.dumps(silence_event))
            
        except Exception as e:
            LOGGER.error("Function execution error: %s", e)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
