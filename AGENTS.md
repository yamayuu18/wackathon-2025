# AGENTS.md

このドキュメントは、複数のAIエージェントが Wackathon 2025 プロジェクトで協働する際のガイドラインです。
**全てのやり取り、計画書（Implementation Plan）、成果物（Walkthrough）、およびコード内のコメントは日本語で記述してください。**
既存ドキュメントの知見を尊重してください。

## プロジェクト概要
- PC カメラで 5 秒ごとに撮影し、`camera/captured_images/` に保存。将来的に AWS S3 → Lambda → Rekognition → Polly へ連携する想定。
- obniz 超音波センサーが計測値を Google Apps Script に送信し、システム全体のトリガーに利用。
- 主要スクリプト: `camera/camera_capture.py`（ローカル保存）、`camera/config.py`（撮影設定・AWS 設定）、`obniz/index.html`（距離センサー連携）。

## 共通ルール
1. 変更前に `README.md` と `CLAUDE.md` を確認し、既存の意図やスタイルを踏襲する。
2. Python コードは PEP 8 / 型ヒント / Google Docstring（`CLAUDE.md` 参照）を守る。
3. 開発中は `pip install -r requirements.txt` で依存関係を揃え、`cd camera && python camera_capture.py` で挙動確認する。
4. AWS 連携は未実装。仮想コードや資格情報はダミー値で書かず、コメントで TODO 管理する。
5. 機密データ（画像、AWS キー等）はリポジトリに含めない。環境変数または `.env` の利用を明示する。

## エージェント構成と責務

### 1. Navigator（要件整理・戦略担当）
- 最新の課題や想定するユーザーストーリーを洗い出し、スコープと優先順位を定義。
- 既存資料（README、doc/poitokun_mermaid.html など）から制約条件を抽出し、Builder・Guardian に共有。
- 未確定要素（AWS 証明書、S3 バケット名等）は TODO とリスクをセットで明記。

### 2. Builder（実装担当）
- Navigator が整理したタスクを Python/HTML コードに落とし込む。
- `camera/config.py` の設定値・データフローを念頭に、再利用しやすいモジュール化を徹底。
- 実装時はデバッグログよりも例外メッセージ／バリデーションを優先し、必要に応じて `logging` を導入。
- 小さな単位で動作確認し、必要なら `camera/captured_images/` にサンプルを生成したうえで結果を Guardian に報告。

### 3. Guardian（レビュー・品質管理担当）
- PR レベルで差分を確認し、動作リスク・例外ハンドリング・パフォーマンスを重点的にチェック。
- コードスタイル（型ヒント、Docstring、コメント過多の抑制）と設定ファイルの整合性を評価。
- 実機テストや `python camera_capture.py` 実行ログが不足していれば追加で要求。
- バグや仕様逸脱を見つけたら再現手順を記載し、Navigator へフィードバックして要件を再整理する。

## 推奨ワークフロー
1. Navigator が課題・要件を Issue 化し、具体的な受け入れ条件を列挙。
2. Builder が Issue を実装し、最小限の再現手順・テスト結果を添えて提出。
3. Guardian がレビュー・検証を実施し、問題なければマージを承認。必要なら追加のフォローアップ Issue を作成。

## 補足リソース
- `README.md`: 全体像、セットアップ手順、AWS 連携 TODO。
- `CLAUDE.md`: **技術的な詳細はこちら**。コードスタイル、アーキテクチャ、デプロイ手順、テスト方法など。
- `doc/poitokun_mermaid.html`: システム構成図。AWS サービス間の連携を把握する際に参照。

全エージェントは上記方針を守り、進捗や問題点を日本語で明確に共有してください。
