# AWS EC2 デプロイガイド (初心者向け)

このガイドでは、AWS EC2 (Ubuntu) にサーバーを立ち上げ、`ngrok` を使ってHTTPS化する手順を説明します。
**所要時間目安: 30分〜1時間**

## 1. EC2インスタンスの作成

1.  AWSコンソールにログインし、**EC2** のページへ移動します。
2.  「**インスタンスを起動**」をクリックします。
3.  以下の設定で作成します：
    *   **名前**: `wackathon-server` (なんでもOK)
    *   **OS (AMI)**: **Ubuntu Server 24.04 LTS** (または 22.04)
        *   ※ Amazon Linux よりも Ubuntu の方がライブラリ導入が簡単でおすすめです。
    *   **インスタンスタイプ**: `t3.small` (無料枠があれば `t2.micro` でも動きますが、音声処理で少し重くなる可能性があります)
    *   **キーペア**: 「新しいキーペアの作成」→ 名前を付けて `.pem` ファイルをダウンロードします。
        *   **重要**: このファイルはなくさないでください！
    *   **ネットワーク設定**:
        *   「インターネットからのHTTPSトラフィックを許可」にチェック
        *   「インターネットからのHTTPトラフィックを許可」にチェック
4.  「**インスタンスを起動**」をクリックします。

## 2. サーバーへの接続 (SSH)

ターミナル（Mac）を開き、ダウンロードしたキーペア（例: `key.pem`）がある場所へ移動して接続します。

```bash
# 1. キーの権限を変更 (必須)
chmod 400 key.pem

# 2. SSH接続 (パブリックIPアドレスはAWSコンソールで確認)
ssh -i key.pem ubuntu@<パブリックIPアドレス>
```

接続に成功すると、プロンプトが `ubuntu@ip-xxx-xxx-xxx-xxx:~$` に変わります。

## 3. 環境構築

サーバーに入ったら、必要なソフトをインストールします。

```bash
# パッケージリストの更新
sudo apt update

# 必要なツールのインストール
# python3-venv: 仮想環境用
# ffmpeg: 音声処理用
# portaudio19-dev: PyAudioのインストールに必須
# unzip: ngrok解凍用
sudo apt install -y python3-pip python3-venv ffmpeg portaudio19-dev unzip
```

## 4. コードの準備

GitHubからコードを取得します。

```bash
# リポジトリのクローン (HTTPS版のURLを使ってください)
git clone https://github.com/yamayuu18/wackathon-2025.git

# ディレクトリ移動
cd wackathon-2025

# 仮想環境の作成
python3 -m venv .venv

# 仮想環境の有効化
source .venv/bin/activate

# ライブラリのインストール (少し時間がかかります)
pip install -r requirements.txt
```

## 5. 設定ファイル (.env) の作成

Macにある `.env` の内容をコピーして、サーバー上に作成します。

```bash
# nanoエディタでファイル作成
nano .env
```

1.  Macの `.env` の中身を全選択してコピー。
2.  ターミナル画面で貼り付け (Command+V)。
3.  **修正ポイント**:
    *   `AUDIO_ENDPOINT=ar` (ARチームが使うなら `ar` に変更)
    *   `USE_MAC_SPEAKER=false` (サーバー上ではスピーカーを使わないため)
4.  保存して終了: `Ctrl+O` → `Enter` → `Ctrl+X`

## 6. ngrok のセットアップ (Linux版)

HTTPS化のために ngrok をインストールします。

```bash
# ngrokのダウンロード
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list && sudo apt update && sudo apt install ngrok

# 認証 (あなたのngrokトークンを使ってください)
ngrok config add-authtoken <あなたのNGROK_AUTHTOKEN>
```

## 7. サーバーの起動

画面を2つ（または `tmux` 等）使って、サーバーと ngrok を同時に動かします。

### ターミナル1: サーバー起動
```bash
# (SSH接続した状態で)
cd wackathon-2025
source .venv/bin/activate
python3 camera/webapp/server.py
```

### ターミナル2: ngrok起動
（新しいターミナルを開き、再度 SSH 接続してください）
```bash
# 8000番ポートを公開
ngrok http 8000
```

表示された `https://xxxx.ngrok-free.app` が、ARチームに伝えるURLになります。

---

### ヒント: サーバーをずっと動かし続けるには？
SSHを切断しても動かし続けるには `nohup` コマンドを使うか、`tmux` を使うのが便利です。

**簡単な方法 (nohup):**
```bash
# バックグラウンドで起動
nohup python3 camera/webapp/server.py > server.log 2>&1 &

# ログを見る
tail -f server.log

# 停止する
pkill -f server.py
```
