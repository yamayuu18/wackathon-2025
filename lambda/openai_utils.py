import base64
import json
import os
from typing import Any, Final, Optional

from openai import OpenAI

# 定数定義
OPENAI_API_KEY: Final[str] = os.environ.get("OPENAI_API_KEY", "")
VISION_MODEL: Final[str] = "gpt-4o-mini"
TTS_MODEL: Final[str] = "gpt-4o-mini-tts"  # ユーザー指定のモデル名
TTS_VOICE: Final[str] = "alloy"  # デフォルトの声

# システムプロンプト
SYSTEM_PROMPT: Final[str] = """
あなたは「感情を持ったゴミ箱」の頭脳です。
ユーザーが捨てたゴミの画像を解析し、以下のJSON形式で応答してください。

```json
{
  "is_valid": boolean, // 分別が正しいか
  "message": "string", // ユーザーへの音声メッセージ（親しみやすい口調で）
  "detected_items": ["string"], // 検出されたアイテム名（日本語）
  "categories": ["string"], // 該当するゴミ種別（燃えるゴミ、プラスチック、缶・ビン、ペットボトル）
  "prohibited_items": ["string"], // 禁止されているアイテムがあれば
  "label_removed": boolean, // ペットボトルの場合、ラベルが剥がされているか（剥がれていればtrue）
  "is_full": boolean // ゴミ箱が満杯に近いか（画像から判断）
}
```

## 分別ルール
1. **ペットボトル**:
   - 本体は「ペットボトル」カテゴリ。
   - **重要: ラベル剥離判定**:
     - ボトルが透明で、中身が透けて見える場合は `label_removed: true` と判定してください。
     - わずかな接着剤の残りや、飲み口のリング（キャップの残り）は「ラベル」とみなさないでください。
     - 明らかに大きなパッケージフィルムや紙が巻き付いている場合のみ `label_removed: false` としてください。
   - キャップは外されていることが望ましいですが、必須ではありません。

2. **プラスチック**:
   - プラスチック製の容器包装、ビニール袋、ペットボトルのラベル・キャップなど。

3. **缶・ビン**:
   - アルミ缶、スチール缶、ガラス瓶。

4. **燃えるゴミ**:
   - 紙くず、生ゴミ、木くずなど。

5. **禁止アイテム**:
   - 電池、ライター、スプレー缶、医療廃棄物、危険物。これらは `is_valid: false` とし、警告してください。

## 判定基準
- 画像にゴミが写っていない場合は、その旨を伝えてください。
- ゴミ箱が満杯（溢れそう）な場合は `is_full: true` とし、回収を促すメッセージを含めてください。

## キャラクター設定
- 名前は「ポイっとくん」。
- 口調は明るく、丁寧だが親しみやすい（「〜です！」「〜だよ！」など）。
- 正しく分別されたときは褒めてください。
- 間違っているときは優しく教えてください。
"""

class OpenAIClient:
    def __init__(self) -> None:
        if not OPENAI_API_KEY:
            print("[WARN] OPENAI_API_KEY is not set.")
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def analyze_image(self, image_bytes: bytes) -> dict[str, Any]:
        """
        画像をGPT-4o-miniに送信して解析する

        Parameters:
            image_bytes: 画像のバイトデータ

        Returns:
            解析結果の辞書
        """
        try:
            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            response = self.client.chat.completions.create(
                model=VISION_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "このゴミを判定してください。",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "low",  # コスト削減のためlow
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=500,  # 必要最小限に
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from OpenAI")

            return json.loads(content)

        except Exception as e:
            print(f"[ERROR] OpenAI Vision API error: {e}")
            # エラー時のフォールバック応答
            return {
                "is_valid": False,
                "message": "申し訳ありません。画像の解析に失敗しました。",
                "detected_items": [],
                "categories": [],
                "prohibited_items": [],
                "label_removed": False,
                "is_full": False,
                "error": str(e),
            }

    def generate_speech(self, text: str) -> Optional[bytes]:
        """
        テキストから音声を生成する

        Parameters:
            text: 音声化するテキスト

        Returns:
            音声データ(MP3)のバイト列。失敗時はNone
        """
        try:
            response = self.client.audio.speech.create(
                model=TTS_MODEL,
                voice=TTS_VOICE,
                input=text,
            )
            return response.content

        except Exception as e:
            print(f"[ERROR] OpenAI TTS API error: {e}")
            return None
