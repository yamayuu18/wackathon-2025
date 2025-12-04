# ARクライアント 音声入出力実装ガイド

このドキュメントは、ARチーム（初心者向け）が「ポイっとくん」の音声機能（マイク入力・スピーカー出力）を実装するための手順書です。

## 1. システムの仕組み
ARクライアントは、サーバー (`server.py`) と **WebSocket** で接続し、以下のやり取りを行います。
- **聞く (Speaker)**: サーバーから送られてくる音声データを受け取り、再生します。
- **話す (Mic)**: マイクで拾った音声をサーバーに送信します。

## 2. 接続情報
- **プロトコル**: WebSocket (WSS)
- **サーバーアドレス**: カメラ側で使用している **ngrokのURL** と同じものを使用します。
    - 例: `wss://xxxx-xx-xx-xx-xx.ngrok-free.app/ws`
- **クエリパラメータ**:
    - `role`: `ar` (**必須**)
    - `token`: サーバー側の `.env` ファイルで設定した `WS_AUTH_TOKEN` の値。
        - **注意**: トークンが未設定だと毎回変わってしまうため、サーバー担当者に `.env` への固定設定を依頼してください。

**接続URLの完全な例**:
```
wss://example.ngrok-free.app/ws?role=ar&token=YOUR_SECRET_TOKEN
```

## 3. 実装ステップ (Webアプリ/JSの場合)

以下は **実装ロジックのサンプル** です。
ARチームが既に持っているHTML/JSファイルの中に、以下の `<script>` タグ内のロジック（特に `initAudio` と `connectWebSocket` 関数）を組み込んでください。

### 必要なライブラリ
特になし（標準の WebSocket と Web Audio API を使用）

### サンプルコード (HTML/JS)
※ これは動作確認用の単体ファイルですが、必要な部分をコピーして既存のARアプリに統合してください。

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AR Audio Client Integration Sample</title>
</head>
<body>
    <!-- 既存のARアプリのUIがあると仮定 -->
    <h1>AR App (Audio Integration)</h1>
    <button id="connectBtn">音声接続開始</button>
    <div id="status">未接続</div>

    <script>
        // ==========================================
        // 1. 設定 (サーバー担当者と共有)
        // ==========================================
        const SERVER_URL = "wss://YOUR_NGROK_URL/ws"; // カメラ側と同じngrok URL
        const TOKEN = "YOUR_TOKEN";                   // .envで設定した共通トークン

        let socket = null;
        let audioContext = null;
        let nextStartTime = 0;

        // ==========================================
        // 2. 統合ポイント: ユーザーアクションで開始
        // ==========================================
        // ブラウザの制限により、音声再生にはユーザー操作(クリック等)が必須です。
        document.getElementById('connectBtn').onclick = async () => {
            await initAudio();
            connectWebSocket();
        };

        // ==========================================
        // 3. 音声処理の初期化 (24kHz)
        // ==========================================
        async function initAudio() {
            // OpenAI Realtime APIに合わせて 24kHz でコンテキストを作成
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
            
            // マイク入力のセットアップ
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const source = audioContext.createMediaStreamSource(stream);
                
                // PCM16変換用プロセッサ
                const processor = audioContext.createScriptProcessor(4096, 1, 1);
                
                source.connect(processor);
                processor.connect(audioContext.destination);

                processor.onaudioprocess = (e) => {
                    if (!socket || socket.readyState !== WebSocket.OPEN) return;

                    const inputData = e.inputBuffer.getChannelData(0);
                    // Float32 -> Int16 (PCM) 変換
                    const pcmData = floatTo16BitPCM(inputData);
                    // Base64変換
                    const base64Audio = arrayBufferToBase64(pcmData);

                    // サーバーへ送信
                    socket.send(JSON.stringify({
                        type: "input_audio_buffer.append",
                        audio: base64Audio
                    }));
                };
            } catch (err) {
                console.error("マイク許可エラー:", err);
                alert("マイクの使用を許可してください");
            }
        }

        // ==========================================
        // 4. WebSocket接続
        // ==========================================
        function connectWebSocket() {
            const url = `${SERVER_URL}?role=ar&token=${TOKEN}`;
            socket = new WebSocket(url);

            socket.onopen = () => {
                document.getElementById('status').innerText = "接続中 (role=ar)";
                console.log("Connected to Server");
            };

            socket.onmessage = async (event) => {
                const data = JSON.parse(event.data);

                // 音声データ受信 (response.audio.delta)
                if (data.type === "response.audio.delta") {
                    playAudio(data.delta);
                }
            };

            socket.onclose = () => {
                document.getElementById('status').innerText = "切断されました";
            };
        }

        // ==========================================
        // 5. 音声再生 (Base64 -> Audio)
        // ==========================================
        function playAudio(base64Data) {
            const binaryString = atob(base64Data);
            const len = binaryString.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            const int16Data = new Int16Array(bytes.buffer);
            const floatData = new Float32Array(int16Data.length);
            
            // Int16 -> Float32 変換
            for (let i = 0; i < int16Data.length; i++) {
                floatData[i] = int16Data[i] / 32768.0;
            }

            // バッファ作成
            const buffer = audioContext.createBuffer(1, floatData.length, 24000);
            buffer.getChannelData(0).set(floatData);

            // 再生キューイング（途切れないように時間を管理）
            const source = audioContext.createBufferSource();
            source.buffer = buffer;
            source.connect(audioContext.destination);

            const currentTime = audioContext.currentTime;
            if (nextStartTime < currentTime) {
                nextStartTime = currentTime;
            }
            source.start(nextStartTime);
            nextStartTime += buffer.duration;
        }

        // ユーティリティ: Float32 -> Int16
        function floatTo16BitPCM(input) {
            const output = new Int16Array(input.length);
            for (let i = 0; i < input.length; i++) {
                let s = Math.max(-1, Math.min(1, input[i]));
                output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            return output.buffer;
        }

        // ユーティリティ: ArrayBuffer -> Base64
        function arrayBufferToBase64(buffer) {
            let binary = '';
            const bytes = new Uint8Array(buffer);
            const len = bytes.byteLength;
            for (let i = 0; i < len; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return window.btoa(binary);
        }
    </script>
</body>
</html>
```

## 4. サーバー側の設定変更（重要）
AR側で音声を担当する場合、サーバー (`server.py`) の設定を変更する必要があります。
サーバー担当者に以下を依頼してください。

1.  `.env` ファイルの `AUDIO_ENDPOINT` を変更する。
    ```bash
    # .env
    AUDIO_ENDPOINT=ar
    ```
    ※ これにより、AIの音声がカメラ(iPhone)ではなくARクライアントに送られるようになります。

## 5. Unity (C#) の場合
もしUnityを使用している場合は、`NativeWebSocket` などのライブラリを使用し、同様のロジックを実装してください。

- **受信**: `response.audio.delta` の `delta` (Base64) をデコード → PCM(Int16) → AudioClipとして再生。
- **送信**: `Microphone.Start` で取得したデータ → PCM(Int16) → Base64 → `input_audio_buffer.append` として送信。
- **サンプリングレート**: **24,000Hz** に合わせる必要があります（またはリサンプリング）。

---
**不明点があれば、サーバー担当者（Navigator/Builder）に「WebSocketのログが見たい」と相談してください。**
