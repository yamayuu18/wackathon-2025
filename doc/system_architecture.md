# システム構成図 (System Architecture)

```mermaid
graph TD
    subgraph local["ローカル環境 (Mac & iPhone)"]
        iPhone_Cam["iPhone (連係カメラ)"] -->|映像入力| Script_Camera[camera_to_s3_mfa.py]
        
        subgraph mac[Mac]
            Script_Camera -->|画像保存| Local_Images[("captured_images/")]
            Script_Camera -->|MFA認証 & アップロード| S3_Images
            
            Script_App["app.py (Flask Server)"] -->|ポーリング 1s| S3_Results
            Script_App -->|音声合成リクエスト| Voicevox["Voicevox Engine"]
            Voicevox -->|WAVデータ| Script_App
            Script_App -->|再生 afplay| Mac_Speaker["Mac スピーカー"]
        end
        
        iPhone_Browser["iPhone (Safari)"] -.->|ステータス確認 Optional| Script_App
    end

    subgraph aws[AWS Cloud]
        S3_Images["S3 Bucket\n(Images)"] -->|Event Trigger| Lambda["Lambda Function\n(waste_validator)"]
        Lambda -->|解析結果 JSON| S3_Results["S3 Bucket\n(Results)"]
    end

    subgraph api[外部 API]
        Lambda -->|画像解析 Vision| OpenAI["OpenAI API\n(GPT-4o-mini)"]
    end

    %% Styling
    style local fill:#e6f3ff,stroke:#333,stroke-width:2px
    style aws fill:#fff0e6,stroke:#333,stroke-width:2px
    style api fill:#e6ffe6,stroke:#333,stroke-width:2px
    
    style Script_Camera fill:#ff9999,stroke:#333,color:black
    style Script_App fill:#99ccff,stroke:#333,color:black
    style Lambda fill:#ffcc99,stroke:#333,color:black
```

## 処理フロー詳細

1.  **画像取得**: `camera_to_s3_mfa.py` がiPhoneの連係カメラを使用してx秒ごとに写真を撮影。
2.  **アップロード**: 撮影した画像を AWS S3 (`wackathon-2025-trash-images`) にアップロード。
3.  **解析実行**: S3へのアップロードをトリガーに Lambda が起動。OpenAI API で画像を解析。
4.  **結果保存**: Lambda が解析結果（メッセージ、判定など）を JSON ファイルとして S3 (`wackathon-2025-voice-responses/results/`) に保存。
5.  **結果検知**: `app.py` が S3 を監視しており、新しい JSON ファイルを見つけるとダウンロード。
6.  **音声生成**: `app.py` がローカルの Voicevox にテキストを送り、音声データ (WAV) を生成。
7.  **音声再生**: 生成された音声を Mac のスピーカーから再生 (`afplay`)。
