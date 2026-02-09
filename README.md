# 見積RAGシステム

過去の見積データを蓄積し、Mattermostから自然言語で問い合わせることで、類似案件の検索と概算見積を提示するシステム。

## 構成

- **rag-api** — FastAPI (Python 3.12) + uvicorn
- **Qdrant** — ベクトルDB (類似検索)
- **Gemini API** — Embedding生成 + LLM回答生成
- **Mattermost** — ユーザーインターフェース (Webhook連携)

## 前提条件

- Docker / Docker Compose がインストール済み
- Caddy（リバースプロキシ）が `localproxy` ネットワークで稼働中
- 独自ドメインのDNS設定が可能
- Google Gemini APIキーを取得済み
- Mattermostが稼働中（Webhook設定が可能）

## VPSへのデプロイ手順

### 1. リポジトリを配置

```bash
git clone <repo-url> ~/estimate-rag
cd ~/estimate-rag
```

### 2. 環境変数を設定

```bash
cp .env.example .env
nano .env
```

| 変数 | 説明 |
|------|------|
| `GEMINI_API_KEY` | Google Gemini APIキー |
| `MATTERMOST_API_URL` | Mattermost API URL (例: `https://mattermost.example.com/api/v4`) |
| `MATTERMOST_BOT_TOKEN` | Bot Token (ファイルダウンロード用) |
| `MATTERMOST_INCOMING_WEBHOOK_URL` | Incoming Webhook URL (回答投稿用) |
| `MATTERMOST_OUTGOING_WEBHOOK_TOKEN` | Outgoing Webhook検証トークン |

### 3. DNSにAレコードを追加

使用するサブドメイン（例: `estimate.example.com`）をVPSのIPアドレスに向ける。

### 4. Caddyfileにエントリを追加

Caddyの設定ファイルに以下を追記：

```
estimate.example.com {
    reverse_proxy rag-api:8000
}
```

Caddyを再読み込み：

```bash
docker exec <caddy-container> caddy reload --config /etc/caddy/Caddyfile
```

### 5. 起動

```bash
cd ~/estimate-rag
docker compose up -d --build
```

### 6. 動作確認

```bash
curl https://estimate.example.com/api/v1/health
```

正常時のレスポンス：

```json
{"status": "healthy", "qdrant": "connected", "gemini": "available"}
```

### 7. Mattermost側の設定

1. **Outgoing Webhook** を作成し、コールバックURLを設定：
   `https://estimate.example.com/api/v1/webhook/mattermost`
2. トリガーワード: `@見積`
3. 取得したトークンを `.env` の `MATTERMOST_OUTGOING_WEBHOOK_TOKEN` に設定
4. コンテナを再起動: `docker compose restart rag-api`

## Dockerネットワーク

Caddyと同じ `localproxy` 外部ネットワークを使用します。ネットワークがない場合は事前に作成してください：

```bash
docker network create localproxy
```

## 使い方

### Mattermostコマンド

| コマンド | 動作 |
|----------|------|
| `@見積 <質問>` | 類似見積を検索して概算を回答 |
| `@見積 インポート` + CSV添付 | CSVデータを取り込み |
| `@見積 件数` | 登録データ件数を表示 |

### デバッグ用API

```bash
# CSV取り込み
curl -X POST http://localhost:8000/api/v1/data/import -F "file=@sample_data.csv"

# 検索
curl "http://localhost:8000/api/v1/data/search?q=SUS304+シャフト"

# 件数
curl http://localhost:8000/api/v1/data/count

# ヘルスチェック
curl http://localhost:8000/api/v1/health
```

## CSV仕様

```csv
id,name,material,diameter_mm,length_mm,weight_kg,application,grade,price,quantity,unit_price,customer,notes,estimate_date
```

- 文字コード: UTF-8 (BOMあり/なし両対応)
- 必須列: `id`, `name`, `material`, `diameter_mm`, `length_mm`, `application`, `price`
- `.xlsx` 形式にも対応 (1シート目を読み取り)

## ディレクトリ構成

```
estimate-rag/
├── docker-compose.yml
├── .env
├── sample_data.csv
├── docs/
│   └── estimate-rag-spec.md
└── rag-api/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py
    ├── config.py
    ├── routers/
    │   ├── webhook.py        # Mattermost Webhook処理
    │   └── search.py         # デバッグ用API
    ├── services/
    │   ├── gemini_client.py  # Geminiクライアント (共有)
    │   ├── embedding.py      # Embedding生成
    │   ├── llm.py            # LLM回答生成
    │   ├── qdrant.py         # Qdrant操作
    │   ├── filter.py         # メタデータフィルタ抽出
    │   ├── rag.py            # RAGパイプライン
    │   ├── parser.py         # CSV/Excelパーサー
    │   └── mattermost.py     # Mattermost API連携
    ├── models/
    │   └── estimate.py       # データモデル
    └── prompts/
        └── system.txt        # システムプロンプト
```

## 詳細仕様

[docs/estimate-rag-spec.md](docs/estimate-rag-spec.md) を参照。
