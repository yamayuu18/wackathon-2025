# データベース定義書 (Database Schema)

## 概要
本システムでは、ゴミの廃棄履歴を **AWS DynamoDB** に保存します。
スキーマレスなNoSQLですが、アプリケーション側で以下のデータ構造を定義して使用しています。

## DynamoDB テーブル設定

| 項目 | 設定値 | 備考 |
| :--- | :--- | :--- |
| **Table Name** | `waste_disposal_history` | 環境変数 `DYNAMODB_TABLE_NAME` で変更可能 |
| **Partition Key** | `user_id` (String) | ユーザー識別子（現状は固定値 `webapp_user`） |
| **Sort Key** | `timestamp` (String) | ISO 8601形式の日時文字列 |
| **Region** | `ap-northeast-1` (Tokyo) | |

## データ項目定義 (Items)

各レコードには以下の属性が含まれます。

| 属性名 (Attribute) | 型 (Type) | 必須 | 説明 |
| :--- | :--- | :--- | :--- |
| `user_id` | String | Yes | **(Partition Key)** ユーザーID。Webアプリ版では `webapp_user` 固定。 |
| `timestamp` | String | Yes | **(Sort Key)** 記録日時。例: `2025-11-30T06:00:00.123456` |
| `image_path` | String | Yes | 画像の保存パスまたはセッション識別子。例: `webapp_session` |
| `detected_items` | List[String] | No | 検出されたゴミの種類。例: `["ペットボトル"]` |
| `is_valid` | Boolean | Yes | 判定結果。`true` (OK), `false` (NG) |
| `rejection_reason` | String | No | NGの場合の理由コード。<br>・`wrong_item`: ペットボトル以外<br>・`has_cap`: キャップあり<br>・`has_label`: ラベルあり<br>・`dirty`: 汚れ・中身あり |
| `has_change` | Boolean | Yes | **(New)** 画像に変化があったかどうか。<br>・`true`: 新しいゴミや物体が検出された<br>・`false`: 手ブレや光の加減のみ（AIは無言） |
| `message` | String | No | ユーザーへのフィードバックメッセージ（関西弁）。 |
| `raw_json` | String | Yes | 上記を含む判定結果全体のJSON文字列（バックアップ用）。 |

## JSON構造例 (`raw_json` の中身)

ARチーム等の他システム連携時は、このJSON構造を参照してください。

```json
{
  "detected_items": ["ペットボトル"],
  "is_valid": false,
  "rejection_reason": "has_cap",
  "has_change": true,
  "message": "アカン、キャップついてるやんけ！"
}
```

### `has_change` の活用について
*   **`true` の場合**: 実際にゴミが捨てられた（または試みられた）イベントです。AR側でキャラクターのアニメーションを再生してください。
*   **`false` の場合**: ユーザーがカメラを構えているだけ、または手ブレによる誤検知です。**AR側では何もアクションを起こさないでください。**
