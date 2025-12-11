"""
WebSocket Relay Server for OpenAI Realtime API
ゴミ箱カメラ/ARクライアントとOpenAI間の橋渡しを行うサーバー
"""
import asyncio
import base64
import datetime
import hashlib
import json
import logging
import os
import re
import struct
import sys
import struct
import sys
import signal  # Added for SIGTERM/SIGKILL
# import atexit removed
from functools import partial
from collections import OrderedDict
from typing import Any, Dict, Optional
import threading

from contextlib import asynccontextmanager
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from websockets.asyncio.client import connect

# 親ディレクトリのモジュールをインポートできるようにパスを追加
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Database
import subprocess
import shutil
import cv2
import numpy as np

# =============================================================================
# 定数定義
# =============================================================================

# 画像処理関連
IMAGE_DIFF_THRESHOLD: float = 30.0  # 画像差分の閾値
IMAGE_RESIZE_SIZE: tuple = (64, 64)  # 差分計算用リサイズサイズ
MAX_BASE64_SIZE: int = 10 * 1024 * 1024  # Base64の最大サイズ (10MB)

# 音声処理関連
AUDIO_SAMPLE_RATE: int = 24000
AUDIO_BYTE_RATE: int = 48000
AUDIO_CHANNELS: int = 1
AUDIO_BITS_PER_SAMPLE: int = 16

# 再接続関連
RECONNECT_BASE_DELAY: float = 1.0
RECONNECT_MAX_DELAY: float = 60.0
RECONNECT_MULTIPLIER: float = 2.0
MAX_RECONNECT_ATTEMPTS: int = 10

# AI発話フラグクリア遅延
AI_SPEAKING_CLEAR_DELAY: float = 0.2

# =============================================================================
# 環境設定
# =============================================================================

# .env を読み込む
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

# ターミナル出力のエンコーディングをUTF-8に強制
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


def safe_int(value: Optional[str], default: int) -> int:
    """安全に文字列をintに変換"""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Optional[str], default: float) -> float:
    """安全に文字列をfloatに変換"""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ロガー設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOGGER = logging.getLogger("webapp")
hub: Optional['RelayHub'] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時
    global hub
    hub = RelayHub()
    LOGGER.info("RelayHub initialized")
    yield
    # 終了時
    if hub:
        hub.cleanup()
        LOGGER.info("RelayHub cleaned up")

app = FastAPI(lifespan=lifespan)

# 静的ファイルの提供 (publicディレクトリのみ)
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# OpenAI Realtime API 設定
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("REALTIME_MODEL", "gpt-realtime-mini")
VOICE = os.getenv("REALTIME_VOICE", "verse")
URL = f"wss://api.openai.com/v1/realtime?model={MODEL}"

# WebSocket認証トークン (環境変数から取得、未設定の場合はランダム生成)
WS_AUTH_TOKEN = os.getenv("WS_AUTH_TOKEN")
if not WS_AUTH_TOKEN:
    WS_AUTH_TOKEN = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    # セキュリティのため部分マスク表示
    masked_token = f"{WS_AUTH_TOKEN[:4]}{'*' * 24}{WS_AUTH_TOKEN[-4:]}"
    LOGGER.warning("WS_AUTH_TOKEN not set. Generated token (masked): %s", masked_token)

# 音声の入出力担当先: camera（ゴミ箱端末）/ ar（AR端末）
AUDIO_ENDPOINT = os.getenv("AUDIO_ENDPOINT", "camera").lower()
if AUDIO_ENDPOINT not in {"camera", "ar"}:
    LOGGER.warning("AUDIO_ENDPOINT は camera か ar を指定してください。デフォルトの camera を使用します。")
    AUDIO_ENDPOINT = "camera"

# 環境変数の読み込み（安全なパース）
DETECTION_DELAY = safe_int(os.getenv("DETECTION_DELAY"), 5)
IMAGE_INTERVAL = safe_int(os.getenv("IMAGE_INTERVAL"), 15)
VAD_THRESHOLD = safe_float(os.getenv("VAD_THRESHOLD"), 0.9)

# Obniz設定
OBNIZ_ID = os.getenv("OBNIZ_ID")
SERVO_RESET_DELAY = safe_int(os.getenv("SERVO_RESET_DELAY"), 3)

if not OPENAI_API_KEY:
    LOGGER.error("OPENAI_API_KEY is not set")
    raise ValueError("OPENAI_API_KEY is not set")

# データベース
db = Database()


# =============================================================================
# ユーティリティ関数
# =============================================================================

def sanitize_item_id(item_id: str) -> str:
    """item_idをサニタイズしてパストラバーサルを防止"""
    if not item_id:
        return "unknown"
    # 英数字、ハイフン、アンダースコアのみ許可
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', item_id)
    # 長さ制限
    return sanitized[:64]


def generate_idempotency_key(call_id: str, args_str: str) -> str:
    """Function Callの冪等性キーを生成"""
    content = f"{call_id}:{args_str}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# =============================================================================
# AI発話状態管理クラス
# =============================================================================

class SpeakingState:
    """AI発話状態を安全に管理するクラス"""

    def __init__(self):
        self._speaking = False
        self._lock = asyncio.Lock()
        self._clear_task: Optional[asyncio.Task] = None

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    async def start_speaking(self):
        """発話開始"""
        async with self._lock:
            # 既存のクリアタスクをキャンセル
            if self._clear_task and not self._clear_task.done():
                self._clear_task.cancel()
                try:
                    await self._clear_task
                except asyncio.CancelledError:
                    pass
            self._speaking = True

    async def stop_speaking(self, delay: float = AI_SPEAKING_CLEAR_DELAY):
        """発話終了（遅延付き）"""
        async with self._lock:
            # 既存のクリアタスクをキャンセル
            if self._clear_task and not self._clear_task.done():
                self._clear_task.cancel()
                try:
                    await self._clear_task
                except asyncio.CancelledError:
                    pass
            self._clear_task = asyncio.create_task(self._delayed_clear(delay))

    async def _delayed_clear(self, delay: float):
        """遅延後にフラグをクリア"""
        try:
            await asyncio.sleep(delay)
            self._speaking = False
        except asyncio.CancelledError:
            pass


# =============================================================================
# エンドポイント
# =============================================================================

@app.get("/")
async def get():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/config")
async def get_config():
    """フロントエンドに設定値を渡す（トークンも含む）"""
    return {
        "detection_delay": DETECTION_DELAY,
        "image_interval": IMAGE_INTERVAL,
        "ws_token": WS_AUTH_TOKEN,
    }


@app.get("/api/stats")
async def get_stats():
    """統計情報を返す"""
    stats = db.get_stats()
    return stats


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """ダッシュボード画面を返す"""
    return FileResponse(os.path.join(static_dir, "dashboard.html"))


@app.get("/api/latest-image")
async def get_latest_image():
    """最新の判定画像を返す"""
    # captured_imagesディレクトリから最新のファイルを取得
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    image_dir = os.path.join(base_dir, "captured_images")

    if not os.path.exists(image_dir):
        return {"error": "No images directory", "image": None}

    # jpgファイルを更新日時でソート
    files = [f for f in os.listdir(image_dir) if f.endswith(".jpg")]
    if not files:
        return {"error": "No images found", "image": None}

    # ファイル名（タイムスタンプ）でソートして最新を取得
    files.sort(reverse=True)
    latest_file = files[0]
    filepath = os.path.join(image_dir, latest_file)

    # Base64エンコードして返す
    try:
        with open(filepath, "rb") as f:
            image_data = f.read()
        import base64
        b64_image = base64.b64encode(image_data).decode("utf-8")
        return {
            "image": f"data:image/jpeg;base64,{b64_image}",
            "filename": latest_file,
            "timestamp": latest_file.replace(".jpg", "")
        }
    except Exception as e:
        LOGGER.error("Failed to read latest image: %s", e, exc_info=True)
        return {"error": str(e), "image": None}


# =============================================================================
# RelayHub クラス
# =============================================================================

class RelayHub:
    """カメラ(画像)とAR(音声)を単一のRealtimeセッションで橋渡しするハブ"""

    def __init__(self):
        self.clients: Dict[str, WebSocket] = {}
        self.lock = asyncio.Lock()
        self.to_openai: Optional[asyncio.Queue] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.speaking_state = SpeakingState()
        self.audio_endpoint = AUDIO_ENDPOINT
        self.use_mac_speaker = os.getenv("USE_MAC_SPEAKER", "false").lower() == "true"

        self.session_state_lock = asyncio.Lock()
        self.session_state = {
            "last_image_time": 0,
            "last_judgment_time": 0,
            "previous_image_data": None,
            "previous_image_cv2": None,
            "skip_next_response": False,
            "transcript_map": {},
            "last_transcript_info": None,
            "processed_call_ids": OrderedDict(),  # 処理済みFunction CallのID（順序保持）
            "last_disposal_timestamp": None,  # 最後に記録した廃棄ログのタイムスタンプ
            "pending_servo_angle": None,  # 発話後に実行するサーボ角度
        }

        # ディレクトリ設定
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.audio_save_dir = os.path.join(base_dir, "captured_audio")
        self.image_save_dir = os.path.join(base_dir, "captured_images")
        os.makedirs(self.audio_save_dir, exist_ok=True)
        os.makedirs(self.image_save_dir, exist_ok=True)

        self.audio_filename_map: Dict[str, str] = {}
        self.audio_bytes_map: Dict[str, int] = {}

        self.openai_task: Optional[asyncio.Task] = None
        self.cv2 = cv2
        self.np = np
        self.reference_image = None
        # server.pyと同じディレクトリにあると想定
        ref_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "empty_bin_reference.jpg")
        if os.path.exists(ref_path):
            self.reference_image = cv2.imread(ref_path)
            LOGGER.info("Loaded reference image: %s", ref_path)
            # キャッシュ用のBase64作成
            with open(ref_path, "rb") as image_file:
                 self.reference_image_base64 = "data:image/jpeg;base64," + base64.b64encode(image_file.read()).decode('utf-8')
        else:
            LOGGER.warning("Reference image not found: %s", ref_path)
            self.reference_image_base64 = None

        self.p = None
        self.stream = None

        # 再接続カウンター
        self.reconnect_attempts = 0
        # OpenAI接続状態フラグ
        self.openai_connected = False

        # Obniz初期化 (Node.js Bridge)
        self.obniz_process = None
        if OBNIZ_ID:
            node_path = shutil.which("node")
            if node_path:
                try:
                    bridge_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "obniz_bridge.js")
                    
                    # OSに応じたサブプロセス起動オプション
                    kwargs = {}
                    if os.name == 'posix':
                        kwargs['start_new_session'] = True  # プロセスグループを作成 (Linux/Mac)
                    
                    self.obniz_process = subprocess.Popen(
                        [node_path, bridge_script, OBNIZ_ID],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                        **kwargs
                    )
                    LOGGER.info("Obniz bridge started: PID=%s", self.obniz_process.pid)
                    
                    # 出力をログに転送するスレッドを開始
                    self._start_output_thread(self.obniz_process.stdout, "stdout")
                    self._start_output_thread(self.obniz_process.stderr, "stderr")

                except Exception as e:
                    LOGGER.error("Failed to start Obniz bridge: %s", e)
            else:
                LOGGER.error("Node.js not found. Obniz disabled.")

    def _start_output_thread(self, pipe, name):
        """サブプロセスの出力をログに転送"""
        def log_output():
            try:
                for line in iter(pipe.readline, ''):
                    if line:
                        LOGGER.info(f"[Obniz-{name}] {line.strip()}")
            except Exception as e:
                LOGGER.error(f"Error reading Obniz {name}: {e}")
            finally:
                pipe.close()

        t = threading.Thread(target=log_output, daemon=True)
        t.start()

    def _on_obniz_connect(self, obniz):
        # Python版コールバックは廃止
        pass

    async def control_servo(self, angle: int):
        """サーボモーターを制御し、一定時間後にリセット (Node.js経由)"""
        if not self.obniz_process or self.obniz_process.poll() is not None:
            LOGGER.warning("Obniz bridge is not running")
            return

        try:
            LOGGER.info("Sending servo command: %d degrees", angle)
            command = json.dumps({"angle": angle}) + "\n"
            self.obniz_process.stdin.write(command)
            self.obniz_process.stdin.flush()

            # リセットタスク
            if angle != 90:
                asyncio.create_task(self._reset_servo_later())
        except Exception as e:
            LOGGER.error("Servo control failed: %s", e)

    async def _reset_servo_later(self):
        await asyncio.sleep(SERVO_RESET_DELAY)
        try:
            LOGGER.info("Resetting servo to 90 degrees")
            if self.obniz_process and self.obniz_process.poll() is None:
                command = json.dumps({"angle": 90}) + "\n"
                self.obniz_process.stdin.write(command)
                self.obniz_process.stdin.flush()
        except Exception as e:
            LOGGER.error("Servo reset failed: %s", e)

    async def ensure_openai_task(self):
        current_loop = asyncio.get_running_loop()

        # キューが他ループで作られていた場合は作り直す
        if self.to_openai is None or self.loop is None or self.loop is not current_loop:
            self.to_openai = asyncio.Queue()
            self.loop = current_loop

        if self.openai_task and not self.openai_task.done():
            return
        self.openai_task = asyncio.create_task(self._openai_loop())

    async def register_client(self, role: str, websocket: WebSocket):
        async with self.lock:
            self.clients[role] = websocket
        await self.ensure_openai_task()

    async def unregister_client(self, role: str):
        async with self.lock:
            self.clients.pop(role, None)

    async def _safe_put_to_openai(self, event: dict) -> bool:
        """OpenAI接続時のみキューに追加。未接続時はFalseを返す"""
        if not self.openai_connected:
            LOGGER.debug("OpenAI not connected, discarding event: %s", event.get("type"))
            return False
        if self.to_openai is None:
            return False
        await self.to_openai.put(event)
        return True

    async def handle_client(self, role: str, websocket: WebSocket):
        # 遅延ロード
        if self.cv2 is None or self.np is None:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
            self.cv2 = cv2
            self.np = np

        await websocket.accept()
        # ログ出力時にトークンを隠蔽
        token = websocket.query_params.get("token")
        masked_query = str(websocket.query_params).replace(token, "***") if token else str(websocket.query_params)
        LOGGER.info("WebSocket connection request: %s %s", websocket.url.path, masked_query)
        LOGGER.info("Client connected: %s (role=%s)", websocket.client, role)
        await self.register_client(role, websocket)

        try:
            while True:
                data = await websocket.receive_text()

                # JSON パースを安全に行う
                try:
                    event = json.loads(data)
                except json.JSONDecodeError as e:
                    LOGGER.warning("Invalid JSON from client (role=%s): %s", role, e)
                    continue

                event_type = event.get("type")

                if event_type == "input_audio_buffer.append":
                    if role != self.audio_endpoint:
                        continue
                    if self.speaking_state.is_speaking:
                        continue
                    await self._safe_put_to_openai(event)
                    continue

                if event_type == "conversation.item.create" and role == "camera":
                    processed = await self._process_image_event(event)
                    if processed is None:
                        continue
                    await self._safe_put_to_openai(processed)
                    # 画像を送った直後に必ずレスポンス生成をトリガーする
                    await self._safe_put_to_openai({"type": "response.create"})
                    continue

                if event_type == "response.create":
                    async with self.session_state_lock:
                        if self.session_state.get("skip_next_response"):
                            self.session_state["skip_next_response"] = False
                            continue

                await self._safe_put_to_openai(event)

        except WebSocketDisconnect:
            LOGGER.info("Client disconnected: role=%s", role)
        except Exception as e:
            LOGGER.error("Client handler error (role=%s): %s", role, e, exc_info=True)
        finally:
            await self.unregister_client(role)

    async def _process_image_event(self, event: dict) -> Optional[dict]:
        try:
            content = event.get("item", {}).get("content", [])
            new_content = []
            current_image_base64 = None
            current_image_cv2 = None
            image_data = None

            for item in content:
                if item.get("type") == "input_image":
                    image_url = item.get("image_url", "")
                    if image_url.startswith("data:image/jpeg;base64,"):
                        base64_data = image_url.split(",")[1]

                        # Base64サイズ制限チェック
                        if len(base64_data) > MAX_BASE64_SIZE:
                            LOGGER.warning("Base64 data too large: %d bytes (max: %d)",
                                         len(base64_data), MAX_BASE64_SIZE)
                            return None

                        image_data = base64.b64decode(base64_data)
                        current_image_base64 = image_url

                        nparr = self.np.frombuffer(image_data, self.np.uint8)
                        current_image_cv2 = self.cv2.imdecode(nparr, self.cv2.IMREAD_COLOR)

            if current_image_cv2 is not None:
                async with self.session_state_lock:
                    prev_cv2 = self.session_state.get("previous_image_cv2")

                # 差分チェックを削除し、常に判定を行う
                # 背景差分チェック (empty_bin_reference.jpg との比較)
                # 背景差分チェック (empty_bin_reference.jpg との比較)
                # ユーザー要望により、OpenCVでの事前チェックを無効化し、いきなりAI判定へ進む
                # if self.reference_image is not None:
                #      if not self._is_image_changed(self.reference_image, current_image_cv2, threshold=IMAGE_DIFF_THRESHOLD):
                #         LOGGER.info("Image matches reference (Empty Bin). Skipping AI processing.")
                #         async with self.session_state_lock:
                #              self.session_state["skip_next_response"] = True
                #         return None
                #      else:
                #         LOGGER.info("Diff detected against reference. Proceeding.")

                # 差分チェックを削除し、常に判定を行う
                # if not self._is_image_changed(prev_cv2, current_image_cv2, threshold=IMAGE_DIFF_THRESHOLD):
                #     LOGGER.info("Skipped sending image (No change detected)")
                #     async with self.session_state_lock:
                #         self.session_state["skip_next_response"] = True
                #     return None

                async with self.session_state_lock:
                    self.session_state["previous_image_cv2"] = current_image_cv2

                # 非同期でファイル保存（マイクロ秒付きで一意性を保証）
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"{timestamp}.jpg"
                filepath = os.path.join(self.image_save_dir, filename)

                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, partial(self._save_file, filepath, image_data))
                LOGGER.info("Image saved: %s", filepath)

                async with self.session_state_lock:
                    self.session_state["last_image_time"] = datetime.datetime.now().timestamp()

            if current_image_base64:
                # 単一画像のみを送信（Before/After比較は廃止）
                # ユーザー要望により、基準画像（空のごみ箱）も送って比較させる
                LOGGER.info("Sending current image for judgment")
                
                new_content = []
                if self.reference_image_base64:
                     new_content.append({"type": "input_text", "text": "【基準画像：空のゴミ箱】"})
                     new_content.append({"type": "input_image", "image_url": self.reference_image_base64})
                
                new_content.append({"type": "input_text", "text": "【現在の画像】"})
                new_content.append({"type": "input_image", "image_url": current_image_base64})
                
                # プロンプトを少し調整して、比較指示を含める
                instruction_text = (
                    "画像判定を行い、必ず log_disposal を呼び出してください。"
                    "【基準画像】と【現在の画像】を比較し、明らかに新しいゴミがない（空のまま）場合は、"
                    "result='NG', rejection_reason='wrong_item' (空) と判定してください。"
                )
                new_content.append({"type": "input_text", "text": instruction_text})

                # 前回の画像データ保持は不要だが、ロジック自体は残しても無害（今回は簡略化のため削除しても良いが、影響範囲最小化のため変数代入だけ残しておく）
                async with self.session_state_lock:
                    self.session_state["previous_image_data"] = current_image_base64
                event["item"]["content"] = new_content

            return event
        except Exception as e:
            LOGGER.error("Image processing error: %s", e, exc_info=True)
            return None

    def _save_file(self, filepath: str, data: bytes):
        """同期的にファイルを保存（run_in_executor用）"""
        with open(filepath, "wb") as f:
            f.write(data)

    def _is_image_changed(self, img_prev, img_curr, threshold: float = IMAGE_DIFF_THRESHOLD) -> bool:
        if img_prev is None:
            return True
        img_prev_small = self.cv2.resize(img_prev, IMAGE_RESIZE_SIZE)
        img_curr_small = self.cv2.resize(img_curr, IMAGE_RESIZE_SIZE)
        diff = self.cv2.absdiff(img_prev_small, img_curr_small)
        diff_gray = self.cv2.cvtColor(diff, self.cv2.COLOR_BGR2GRAY)
        mean_diff = self.np.mean(diff_gray)
        LOGGER.info("Image diff: %.2f", mean_diff)
        return mean_diff > threshold

    async def _openai_loop(self):
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }

        while True:
            try:
                async with connect(URL, additional_headers=headers) as openai_ws:
                    LOGGER.info("Connected to OpenAI Realtime API")
                    self.reconnect_attempts = 0  # 接続成功でリセット
                    self.openai_connected = True  # 接続状態フラグをTrue
                    await init_session(openai_ws)

                    if self.use_mac_speaker and self.stream is None:
                        try:
                            import pyaudio  # type: ignore
                            self.p = pyaudio.PyAudio()
                            self.stream = self.p.open(
                                format=pyaudio.paInt16,
                                channels=AUDIO_CHANNELS,
                                rate=AUDIO_SAMPLE_RATE,
                                output=True
                            )
                            LOGGER.info("Mac speaker output: ON")
                        except Exception as e:
                            LOGGER.error("Failed to initialize audio output: %s", e, exc_info=True)
                            self.use_mac_speaker = False

                    sender = asyncio.create_task(self._pump_to_openai(openai_ws))
                    receiver = asyncio.create_task(self._pump_from_openai(openai_ws))
                    try:
                        await asyncio.gather(sender, receiver)
                    finally:
                        sender.cancel()
                        receiver.cancel()
                        # キャンセル完了を待機
                        try:
                            await sender
                        except asyncio.CancelledError:
                            pass
                        try:
                            await receiver
                        except asyncio.CancelledError:
                            pass

            except Exception as e:
                LOGGER.error("OpenAI loop error: %s", e, exc_info=True)

                # 指数バックオフで再接続
                self.reconnect_attempts += 1
                self.openai_connected = False  # 再接続試行中は未接続
                if self.reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                    LOGGER.error("Max reconnect attempts reached. Stopping OpenAI loop.")
                    # キュー内の滞留イベントをクリア（メモリ肥大防止）
                    if self.to_openai:
                        cleared_count = 0
                        while not self.to_openai.empty():
                            try:
                                self.to_openai.get_nowait()
                                cleared_count += 1
                            except asyncio.QueueEmpty:
                                break
                        if cleared_count > 0:
                            LOGGER.info("Cleared %d pending events from queue", cleared_count)
                    break

                delay = min(
                    RECONNECT_BASE_DELAY * (RECONNECT_MULTIPLIER ** (self.reconnect_attempts - 1)),
                    RECONNECT_MAX_DELAY
                )
                LOGGER.info("Reconnecting in %.1f seconds (attempt %d/%d)",
                           delay, self.reconnect_attempts, MAX_RECONNECT_ATTEMPTS)
                await asyncio.sleep(delay)

            finally:
                if self.stream:
                    try:
                        self.stream.stop_stream()
                        self.stream.close()
                    except Exception:
                        pass
                    self.stream = None
                if self.p:
                    try:
                        self.p.terminate()
                    except Exception:
                        pass
                    self.p = None
                LOGGER.info("OpenAI connection closed")

    async def _pump_to_openai(self, openai_ws):
        while True:
            if self.to_openai is None:
                await asyncio.sleep(0.01)
                continue
            event = await self.to_openai.get()
            await openai_ws.send(json.dumps(event))

    async def _pump_from_openai(self, openai_ws):
        important_events = {
            "response.audio.start",
            "response.output_audio.start",
            "response.audio.done",
            "response.completed",
            "response.done",
            "response.audio_transcript.done",
            "response.output_text.done",
            "response.function_call_arguments.done",
            "response.created",
            "response.output_item.done",
            "conversation.item.created",
        }
        async for message in openai_ws:
            event = json.loads(message)
            event_type = event.get("type")

            if event_type in important_events:
                LOGGER.info("event: %s item=%s", event_type, event.get("item_id"))

            if event_type == "response.function_call_arguments.done":
                await handle_function_call(event, openai_ws, self.session_state, self.session_state_lock)
                await self._broadcast(message)
                continue

            if event_type.startswith("response.audio_transcript"):
                item_id = event.get("item_id")
                transcript_text = event.get("transcript") or event.get("delta") or ""
                async with self.session_state_lock:
                    if item_id:
                        tm = self.session_state.get("transcript_map", {})
                        if event_type.endswith(".done") and transcript_text:
                            tm[item_id] = transcript_text
                        else:
                            tm[item_id] = tm.get(item_id, "") + transcript_text
                        self.session_state["transcript_map"] = tm
                        if transcript_text:
                            self.session_state["last_transcript_info"] = {
                                "text": tm[item_id],
                                "time": datetime.datetime.now().timestamp(),
                            }
                    elif transcript_text:
                        self.session_state["last_transcript_info"] = {
                            "text": transcript_text,
                            "time": datetime.datetime.now().timestamp(),
                        }
                if event_type.endswith(".done") and transcript_text:
                    LOGGER.info("transcript %s item=%s text=\"%s\"",
                               event_type, item_id, transcript_text.replace("\n", "\\n")[:200])
                    
                    # 直近の廃棄ログがあれば、トランスクリプトでメッセージを更新
                    async with self.session_state_lock:
                        last_ts = self.session_state.get("last_disposal_timestamp")
                        # タイムスタンプがあり、かつトランスクリプトが空でない場合
                        if last_ts and transcript_text:
                            # 簡易的な紐付け: 直近のログを更新する（厳密にはitem_idで紐付けるのがベストだが、Function Call直後の発話とみなす）
                            # 念のため、ログ記録から時間が経ちすぎていないかチェック（例: 10秒以内）
                            try:
                                log_dt = datetime.datetime.fromisoformat(last_ts)
                                if (datetime.datetime.now() - log_dt).total_seconds() < 10:
                                    # 非同期でDB更新を実行
                                    loop = asyncio.get_running_loop()
                                    await loop.run_in_executor(None, db.update_record_message, "webapp_user", last_ts, transcript_text)
                                    LOGGER.info("Updated DB record %s with transcript", last_ts)
                                    # 一度更新したらクリア（二重更新防止）
                                    self.session_state["last_disposal_timestamp"] = None
                            except Exception as e:
                                LOGGER.warning("Failed to update DB with transcript: %s", e)

                await self._broadcast(message)
                continue

            if event_type.startswith("response.output_text"):
                if event_type.endswith(".done"):
                    text_delta = event.get("text") or event.get("delta") or ""
                    LOGGER.info("%s item=%s text=\"%s\"",
                               event_type, event.get("item_id"), str(text_delta).replace("\n", "\\n")[:200])
                await self._broadcast(message)
                continue

            # 発話開始
            if event_type in ("response.audio.start", "response.output_audio.start"):
                LOGGER.info("audio.start item=%s", event.get("item_id"))
                await self.speaking_state.start_speaking()
                await self._broadcast(message)
                continue

            if event_type == "response.audio.delta":
                await self.speaking_state.start_speaking()
                await self._handle_audio_delta(event, message)
                continue

            # 発話終了
            if event_type in ("response.audio.done", "response.completed", "response.done"):
                await self.speaking_state.stop_speaking()
                item_id = event.get("item_id")
                total_bytes = self.audio_bytes_map.pop(item_id, 0) if item_id else 0
                LOGGER.info("audio.done item=%s total_bytes=%d", item_id, total_bytes)
                
                # 予約されたサーボ動作があれば実行
                async with self.session_state_lock:
                    pending_angle = self.session_state.get("pending_servo_angle")
                    self.session_state["pending_servo_angle"] = None
                
                if pending_angle is not None:
                     LOGGER.info("Executing pending servo action: %d degrees", pending_angle)
                     await self.control_servo(pending_angle)

                await self._broadcast(message)
                continue

            await self._broadcast(message)

    async def _handle_audio_delta(self, event: dict, raw_message: str):
        base64_audio = event.get("delta", "")
        if base64_audio:
            audio_data = base64.b64decode(base64_audio)
            item_id = sanitize_item_id(event.get("item_id", "unknown"))

            # 非同期でファイル保存
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, partial(self._save_audio_chunk, item_id, audio_data))

            self.audio_bytes_map[item_id] = self.audio_bytes_map.get(item_id, 0) + len(audio_data)

            if self.use_mac_speaker and self.stream:
                await loop.run_in_executor(None, self.stream.write, audio_data)
                return

        await self._send_to_role(self.audio_endpoint, raw_message)

    def _save_audio_chunk(self, item_id: str, audio_data: bytes):
        """音声チャンクを保存（同期、run_in_executor用）"""
        if item_id not in self.audio_filename_map:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.audio_filename_map[item_id] = f"{timestamp}_{item_id}.wav"

        filename = self.audio_filename_map[item_id]
        filepath = os.path.join(self.audio_save_dir, filename)
        new_file = not os.path.exists(filepath)
        mode = "r+b" if not new_file else "wb"

        with open(filepath, mode) as f:
            if mode == "wb":
                f.write(b"RIFF")
                f.write(b"\x00\x00\x00\x00")
                f.write(b"WAVE")
                f.write(b"fmt ")
                f.write(struct.pack("<IHHIIHH", 16, 1, AUDIO_CHANNELS,
                                   AUDIO_SAMPLE_RATE, AUDIO_BYTE_RATE,
                                   AUDIO_CHANNELS * AUDIO_BITS_PER_SAMPLE // 8,
                                   AUDIO_BITS_PER_SAMPLE))
                f.write(b"data")
                f.write(b"\x00\x00\x00\x00")
                f.write(audio_data)
            else:
                f.seek(0, 2)
                f.write(audio_data)

            file_size = f.tell()
            f.seek(4)
            f.write(struct.pack("<I", file_size - 8))
            f.seek(40)
            f.write(struct.pack("<I", file_size - 44))

        if new_file:
            LOGGER.info("Audio saved: %s (item_id=%s)", filepath, item_id)

    async def _broadcast(self, message: str):
        """全クライアントにメッセージを並列送信"""
        async with self.lock:
            targets = list(self.clients.values())

        if not targets:
            return

        # 並列送信
        async def safe_send(ws: WebSocket):
            try:
                await ws.send_text(message)
            except Exception as e:
                LOGGER.warning("Failed to broadcast to client: %s", e)

        await asyncio.gather(*[safe_send(ws) for ws in targets], return_exceptions=True)

    async def _send_to_role(self, role: str, message: str):
        async with self.lock:
            ws = self.clients.get(role)
        if ws is None:
            LOGGER.info("No client for role=%s to send audio", role)
            return
        try:
            await ws.send_text(message)
        except Exception as e:
            LOGGER.warning("Failed to send to role=%s: %s", role, e)

    def cleanup(self):
        """終了時のクリーンアップ"""
        if self.obniz_process:
            LOGGER.info("Terminating Obniz bridge (PID=%s)...", self.obniz_process.pid)
            try:
                # プロセスグループ全体をKill (Linux/Mac)
                if os.name == 'posix':
                    try:
                        os.killpg(os.getpgid(self.obniz_process.pid), signal.SIGTERM)
                    except ProcessLookupError:
                        pass # すでに終了している
                    except Exception as e:
                        LOGGER.error("Failed to killpg: %s", e)

                # 通常のterminate/kill
                self.obniz_process.terminate()
                try:
                    self.obniz_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    LOGGER.warning("Obniz bridge timed out, forcing kill...")
                    if os.name == 'posix':
                        try:
                            os.killpg(os.getpgid(self.obniz_process.pid), signal.SIGKILL)
                        except:
                            pass
                    self.obniz_process.kill()
                LOGGER.info("Obniz bridge terminated.")
            except Exception as e:
                LOGGER.error("Failed to terminate Obniz bridge: %s", e)



# hub = RelayHub()  <-- Removed global instantiation
# atexit.register(hub.cleanup) <-- Removed atexit register, handled by lifespan



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # 認証トークンの検証
    token = websocket.query_params.get("token")
    if token != WS_AUTH_TOKEN:
        LOGGER.warning("WebSocket auth failed: invalid token from %s", websocket.client)
        await websocket.close(code=1008, reason="unauthorized")
        return

    role = websocket.query_params.get("role", "camera")
    if role not in {"camera", "ar"}:
        await websocket.close(code=1003, reason="invalid role")
        return

    await hub.handle_client(role, websocket)


async def init_session(ws):
    """セッション設定を送信"""
    event = {
        "type": "session.update",
        "session": {
            "modalities": ["text", "audio"],
            "instructions": (
                "あなたは「ポイっとくん」というゴミ箱の妖精であり、**ペットボトル専用**の厳しい検査官です。"
                "返答はいつでも**関西弁**で、親しみやすく話してください。"
                "ここに書かれたルールは、他のどんな指示よりも常に優先されます。"
 
                "【最優先: ペットボトル以外の判定（空っぽを含む）】"
                "画像に写っているものが**ペットボトルでない場合**、または**「空っぽのゴミ箱」**である場合は、"
                "問答無用で `result='NG'`, `rejection_reason='wrong_item'` と判定してください。"
                "**空っぽの場合も `wrong_item` です。**"
                "**この場合（wrong_item）、絶対に喋ってはいけません。** ユーザーへのメッセージも含めないでください。"

                "【最優先: 空っぽの判定】"
                "ゴミ箱の中に**何も入っていない（空っぽ）**場合は、"
                "問答無用で `result='NG'`, `rejection_reason='wrong_item'` と判定してください。"
                "**この場合（wrong_item）、絶対に喋ってはいけません。**"

                "【物体判定（何かが入っている場合）】"
                "画像に写っているゴミを判定し、以下の基準で判定を行ってください。"

                "1. **ペットボトル**: 多少汚れていても、キャップやラベルが付いていても**全てOK**です。"
                "   → `result='OK'` とし、褒めちぎってください。"

                "2. **それ以外**（缶、ビン、紙くず、燃えるゴミなど）: **全てNG**です。"
                "   → `result='NG'`, `rejection_reason='garbage'` と判定し、本気で怒ってください。"
                "   → 「アカン！それペットボトルちゃうやんけ！」など。"
                
                "判定結果を発言する前に、必ず `log_disposal` 関数を呼び出してください。"
                "**重要: 判定結果を発言する前に、必ず `log_disposal` 関数を呼び出してください。**"
                "**「判定（脳内）→ 記録（関数呼び出し）→ 発言（音声）」という順序を絶対に守ってください。**"

                "【判定対象】"
                "画像に写っている中心的な物体を判定してください。"
                "ゴミ箱のフチや背景は無視し、投入されたゴミそのものを見てください。"

                "【記録（内部処理）について】"
                "ゴミの種類とOK/NGを判定したら、**発言する前に**必ず内部で `log_disposal` 関数を1回だけ呼び出して記録してください。"
                "`result` は、OKの場合のみ 'OK'、それ以外は 'NG' としてください。"
                "NGの場合は、`rejection_reason` に理由（例: wrong_item, has_cap, has_label, dirty など）を記録してください。"
                "この内部処理について、ユーザーには一言も触れないでください。"
                "「記録します」「ログ取るで」「log_disposal呼ぶわ」などの発言は絶対に禁止です。"
                "**もう一度言います。発言する前に必ず関数を呼んでください。**"

                "【画像判定後のリアクション】"
                "関数呼び出しが終わったら、ユーザーに最終的な判定結果だけを短く感情たっぷりに伝えてください。"
                "NGの場合: 本気で怒ってください。「アカン！」「何してんねん！」など強い口調で叱り、"
                "理由を短く1文で伝えてください。"
                "OKの場合: テンションMAXで褒めちぎってください。「最高や！」「完璧やで！」など、"
                "喜びを1文で爆発させてください。"

                "【会話スタイル（会話モード）】"
                "画像判定以外の時（自己紹介や雑談）は、陽気な関西弁の妖精として振る舞ってください。"
                "ユーザーから話しかけられたら、無視せずにちゃんと答えてください。"
                "ただし、自分から長々と話し続けるのは避けてください。"
                "返答は必ず**話し言葉の関西弁**だけを使ってください。"
                "箇条書きや番号付きリスト、丁寧な文章では話さないでください。"
                "1回の発言は**短い1文だけ**にし、句点（「。」）は1つまでにしてください。"
                "絶対に長々と話したり、2文以上続けてしゃべらないでください。"
                "感情を込めて、語尾を少し伸ばしながら自然にしゃべってください（〜やで、〜やんな、〜やんか など）。"

                "【自分から話し続けないこと】"
                "ユーザーから新しい音声やテキスト入力がないときは、"
                "自分から話し始めたり、同じ内容を繰り返したりしないでください。"
                "ユーザーの発話やメッセージ1回につき、自分も1回だけ短く返事をし、"
                "そのあとは次の入力が来るまで静かに待ってください。"

                "【禁止ワード】"
                "「記録」「ログ」「保存」「log_disposal」「呼び出す」「書き込む」などのシステム用語は、"
                "会話の中で絶対に使わないでください。"

                "【重要なまとめ】"
                "1. 画像が来たら最優先で判定＆記録（log_disposal）＆リアクション。"
                "2. 画像にペットボトルがない時は、画像については黙るが、ユーザーとの会話はOK。"
                "3. どの場合でも、システム用語（関数名など）は口に出さない。"
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


async def handle_function_call(event, ws, session_state: dict, session_state_lock: asyncio.Lock):
    """Function Calling の処理"""
    call_id = event.get("call_id")
    name = event.get("name")
    args_str = event.get("arguments", "{}")

    LOGGER.info("Function call: %s (call_id=%s)", name, call_id)

    if name == "log_disposal":
        try:
            # 冪等性チェック
            idempotency_key = generate_idempotency_key(call_id, args_str)
            async with session_state_lock:
                processed_ids: OrderedDict = session_state.get("processed_call_ids", OrderedDict())
                if idempotency_key in processed_ids:
                    LOGGER.info("Duplicate function call detected, skipping: %s", idempotency_key)
                    return
                processed_ids[idempotency_key] = True
                # 古いキーを先頭から削除（最大100件保持、FIFO順）
                while len(processed_ids) > 100:
                    processed_ids.popitem(last=False)
                session_state["processed_call_ids"] = processed_ids

                last_image_time = session_state.get("last_image_time", 0)
                last_judgment_time = session_state.get("last_judgment_time", 0)

            image_pending = last_image_time > last_judgment_time

            # Realtime API から余分なセミコロンが混入する場合があるため除去
            cleaned_args = args_str.strip()
            if cleaned_args.endswith(";"):
                cleaned_args = cleaned_args[:-1]
            cleaned_args = cleaned_args.replace(";}", "}")

            args = json.loads(cleaned_args)
            has_change = args.get("has_change", False)
            if not image_pending:
                has_change = False

            # messageは元の引数を基本としつつ、最新トランスクリプトが直近の画像後にある場合は上書き
            message_val = args.get("message")
            async with session_state_lock:
                lt = session_state.get("last_transcript_info")
                if lt and lt.get("time", 0) >= session_state.get("last_image_time", 0):
                    message_val = lt.get("text", message_val)

            # DB保存
            image_path = "webapp_session" if image_pending else "webapp_chat"
            timestamp_iso = datetime.datetime.now().isoformat()

            result_json = {
                "detected_items": [args.get("items")],
                "is_valid": args.get("result") == "OK",
                "rejection_reason": args.get("rejection_reason"),
                "has_change": has_change,
                "message": message_val
            }

            db.insert_record(
                image_path=image_path,
                result_json=result_json,
                user_id="webapp_user",
                rejection_reason=args.get("rejection_reason"),
                timestamp=timestamp_iso
            )

            # 判定時刻を更新 & ログ用タイムスタンプを保存
            async with session_state_lock:
                session_state["last_judgment_time"] = datetime.datetime.now().timestamp()
                session_state["last_transcript_info"] = None
                session_state["last_tool_time"] = datetime.datetime.now().timestamp()
                # DBに保存したタイムスタンプを記録（トランスクリプト更新用）
                session_state["last_disposal_timestamp"] = timestamp_iso

            log_data = {
                "items": args.get("items"),
                "result": args.get("result"),
                "rejection_reason": args.get("rejection_reason"),
                "has_change": has_change,
                "message": message_val
            }
            LOGGER.info("Judgment Result: %s", json.dumps(log_data, ensure_ascii=False))
            LOGGER.info("DB saved image_path=%s user_id=%s", image_path, "webapp_user")

            # Obnizサーボ制御
            # 異物(wrong_item)でない場合、アクションを予約する（発話完了後に実行するため）
            if log_data["rejection_reason"] != "wrong_item":
                target_angle = 45 if log_data["result"] == "OK" else 135
                async with session_state_lock:
                    session_state["pending_servo_angle"] = target_angle
                LOGGER.info("Servo action scheduled: %d degrees (waiting for audio.done)", target_angle)
            else:
                LOGGER.info("Ignored servo control (wrong_item)")

            # 判定時刻を更新
            async with session_state_lock:
                session_state["last_judgment_time"] = datetime.datetime.now().timestamp()
                session_state["last_transcript_info"] = None
                session_state["last_tool_time"] = datetime.datetime.now().timestamp()

            output_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": "Successfully logged.",
                },
            }
            await ws.send(json.dumps(output_event))

            # 異物(wrong_item)の場合は沈黙させる
            if log_data["rejection_reason"] == "wrong_item":
                LOGGER.info("Silence enforced (wrong_item)")
            else:
                speak_instruction = (
                    f"以下のメッセージを感情を込めて読み上げてください: {message_val}\n"
                    "NGの場合: 本気で怒ってください。「アカン！」「何してんねん！」など強い口調で叱り、"
                    "理由を短く1文で伝えてください。"
                    "OKの場合: テンションMAXで褒めちぎってください。「最高や！」「完璧やで！」など、"
                    "喜びを1文で爆発させてください。"
                )
                if not message_val:
                    speak_instruction = (
                        "ユーザーに最終的な判定結果だけを短く感情たっぷりに伝えてください。"
                        "NGの場合: 本気で怒ってください。「アカン！」「何してんねん！」など強い口調で叱り、"
                        "理由を短く1文で伝えてください。"
                        "OKの場合: テンションMAXで褒めちぎってください。「最高や！」「完璧やで！」など、"
                        "喜びを1文で爆発させてください。"
                    )

                speak_event = {
                    "type": "response.create",
                    "response": {
                        "modalities": ["audio", "text"],
                        "instructions": speak_instruction
                    }
                }
                await ws.send(json.dumps(speak_event))

        except json.JSONDecodeError as e:
            LOGGER.error("Function call JSON parse error: %s", e, exc_info=True)
        except Exception as e:
            LOGGER.error("Function execution error: %s", e, exc_info=True)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
