import json
import requests
from typing import Optional

class VoicevoxClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 50021):
        self.base_url = f"http://{host}:{port}"

    def generate_audio(self, text: str, speaker_id: int = 1) -> Optional[bytes]:
        """
        Voicevoxで音声を生成する
        
        Parameters:
            text: 読み上げるテキスト
            speaker_id: 話者ID (1: ずんだもん, 2: 四国めたん, etc.)
        
        Returns:
            音声データ(wav)のバイト列、失敗時はNone
        """
        try:
            # 1. 音声合成用クエリの作成
            query_payload = {"text": text, "speaker": speaker_id}
            query_response = requests.post(
                f"{self.base_url}/audio_query",
                params=query_payload
            )
            
            if query_response.status_code != 200:
                print(f"[ERROR] Voicevox query failed: {query_response.text}")
                return None

            query_data = query_response.json()

            # 2. 音声合成の実行
            synth_payload = {"speaker": speaker_id}
            synth_response = requests.post(
                f"{self.base_url}/synthesis",
                headers={"Content-Type": "application/json"},
                params=synth_payload,
                data=json.dumps(query_data)
            )

            if synth_response.status_code != 200:
                print(f"[ERROR] Voicevox synthesis failed: {synth_response.text}")
                return None

            return synth_response.content

        except Exception as e:
            print(f"[ERROR] Voicevox connection failed: {str(e)}")
            return None

if __name__ == "__main__":
    # テスト用
    client = VoicevoxClient()
    audio = client.generate_audio("これはテストです。")
    if audio:
        with open("test.wav", "wb") as f:
            f.write(audio)
        print("test.wav generated")
