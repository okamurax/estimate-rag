# 見積RAGシステム 仕様書

## 1. システム概要

### 目的

過去の見積データ（製品名・材質・サイズ・重量・用途・グレード・価格）を蓄積し、Mattermostから自然言語で問い合わせることで、類似案件の検索と概算見積の提示を行う。

### 全体構成

```
┌──────────────────────────────────────────────────────────┐
│  Docker Network: caddy_net                               │
│                                                          │
│  ┌──────────────┐  Outgoing Webhook (Docker内部通信)     │
│  │  Mattermost  │──POST http://rag-api:8000──→┐          │
│  │  (既存)      │←─POST /hooks/xxx (Incoming)─┐│         │
│  └──────────────┘                             ││         │
│                                               ││         │
│  ┌────────────────────────────────────┐       ││         │
│  │  rag-api コンテナ                  │←──────┘│         │
│  │  uvicorn + FastAPI (Python 3.12)   │────────┘         │
│  │  - Webhook受信 (検索)              │──→ Gemini API    │
│  │  - CSV取り込み (Mattermost経由)    │    (外部HTTPS)   │
│  │  - RAG検索・レスポンス生成         │                  │
│  │  ポート: 8000                      │                  │
│  └────────┬───────────────────────────┘                  │
│           │ qdrant:6333 (サービス名で接続)               │
│  ┌────────▼────────────────┐                             │
│  │  qdrant コンテナ        │                             │
│  │  Qdrant (公式イメージ)  │                             │
│  │  - ベクトル格納・検索   │                             │
│  │  - Dashboard (管理UI)   │                             │
│  │  ポート: 6333           │                             │
│  └─────────────────────────┘                             │
│                                                          │
│  ┌──────────────┐                                        │
│  │  Caddy (既存) │←── HTTPS (443) ── 外部アクセス        │
│  │  - SSL終端    │                                       │
│  │  - Qdrant Dashboard用 Basic認証                       │
│  └──────────────┘                                        │
│                                                          │
│  Jitsi, MeshCentral 等 (既存/予定)                       │
└──────────────────────────────────────────────────────────┘

※ Mattermost ↔ rag-api: Docker内部通信（Caddy経由不要）
※ Qdrant Dashboard: Caddy経由でBasic認証付き外部公開
※ rag-api → Gemini API: 外部HTTPS通信
```

### 役割分担

| ツール                     | 役割                                           |
| -------------------------- | ---------------------------------------------- |
| **Mattermost**                 | 見積検索（`@見積`）、CSVインポート             |
| **Qdrant Dashboard**           | データの一覧・詳細確認・修正・削除（管理者用） |

---

## 2. アーキテクチャ

### コンポーネント一覧

| コンポーネント | 役割                              | 技術                            | Docker       |
| -------------- | --------------------------------- | ------------------------------- | ------------ |
| Caddy          | リバースプロキシ、SSL終端         | Caddy (既存)                    | 既存コンテナ |
| rag-api        | Webhook受信、RAG処理、CSV取り込み | uvicorn + FastAPI (Python 3.12) | 新規コンテナ |
| qdrant         | ベクトル格納・類似検索・Dashboard | Qdrant 公式イメージ             | 新規コンテナ |
| Gemini API     | Embedding生成 + 回答生成          | Google Gemini API               | 外部サービス |
| Mattermost     | ユーザーインターフェース          | Mattermost (既存)               | 既存コンテナ |

### 通信フロー

#### 問い合わせ時

```
1. ユーザーがMattermostで発言（例: 「@見積 SUS304 Φ50×200のシャフト、いくら？」）
2. Outgoing WebhookがRAG API Serverにリクエスト送信
3. RAG API Serverが:
   a. ユーザーのメッセージをGemini Embedding APIでベクトル化
   b. Qdrantで類似見積データを検索（上位5件）
   c. 検索結果 + ユーザーの質問をGemini APIに送信
   d. Geminiが類似案件を元に概算見積を回答
4. Incoming WebhookでMattermostに回答を投稿
```

#### データ取り込み時 (Mattermost経由)

```
1. 管理者がMattermostで「@見積 インポート」とCSV/Excelファイルを添付して投稿
2. Outgoing Webhookでrag-apiにリクエスト送信
3. rag-apiが:
   a. Mattermost API (GET /files/{file_id}) でファイルをダウンロード
   b. ファイルをパースし各行を構造化データに変換
   c. 各レコードをテキスト化してGemini Embedding APIでベクトル化
   d. メタデータ + ベクトルをQdrantにupsert（差分更新）
4. Incoming Webhookで取り込み結果をMattermostに返信
```

---

## 3. データモデル

### 見積データスキーマ

| フィールド    | 型       | 必須 | 説明                  | 例                      |
| ------------- | -------- | ---- | --------------------- | ----------------------- |
| id            | integer  | Yes  | 管理番号（CSVで指定） | `1001`                  |
| name          | string   | Yes  | 製品名・部品名        | `回転シャフト`          |
| material      | string   | Yes  | 材質                  | `SUS304`                |
| diameter_mm   | float    | Yes  | 外径 (mm)             | `50.0`                  |
| length_mm     | float    | Yes  | 長さ (mm)             | `200.0`                 |
| weight_kg     | float    | No   | 重量 (kg)             | `3.1`                   |
| application   | string   | Yes  | 用途                  | `ポンプ用回転軸`        |
| grade         | string   | No   | グレード・等級        | `精密級`                |
| price         | integer  | Yes  | 見積金額 (円)         | `45000`                 |
| quantity      | integer  | No   | 数量                  | `10`                    |
| unit_price    | integer  | No   | 単価 (円)             | `4500`                  |
| customer      | string   | No   | 顧客名                | `A社`                   |
| notes         | string   | No   | 備考                  | `表面処理バフ仕上げ`    |
| estimate_date | date     | No   | 見積日                | `2024-06-15`            |
| created_at    | datetime | 自動 | 登録日時              | `2025-01-15T10:30:00`   |

- IDはCSVで整数の管理番号を指定する（Qdrant Point IDとして直接使用）
- IDが一致するデータが既にある場合はupsert（上書き更新）

### Qdrant格納構造

```json
{
  "id": 1001,
  "vector": [0.012, -0.034, ...],
  "payload": {
    "name": "回転シャフト",
    "material": "SUS304",
    "diameter_mm": 50.0,
    "length_mm": 200.0,
    "weight_kg": 3.1,
    "application": "ポンプ用回転軸",
    "grade": "精密級",
    "price": 45000,
    "quantity": 10,
    "unit_price": 4500,
    "customer": "A社",
    "notes": "表面処理バフ仕上げ",
    "estimate_date": "2024-06-15",
    "text": "回転シャフト SUS304 Φ50×200mm 3.1kg ポンプ用回転軸 精密級 単価4,500円 表面処理バフ仕上げ"
  }
}
```

- `id`: 整数値（CSVのidがそのままQdrant Point IDとなる）
- `vector`: Embedding対象は `text` フィールド（検索に関わるフィールドを自然文に結合）
- `payload`: メタデータとして格納し、フィルタリング検索・結果表示に利用

### Qdrantコレクション設定

| 設定項目        | 値                     |
| --------------- | ---------------------- |
| コレクション名  | `estimates`            |
| ベクトル次元数  | 768                    |
| 距離メトリック  | Cosine                 |

- rag-api起動時にコレクションが存在しなければ自動作成する
- 既に存在する場合はスキップ（データは保持される）

### Embedding対象テキストの生成ルール

以下のフィールドのみをテキスト化してEmbeddingの入力とする:

```
{name} {material} Φ{diameter_mm}×{length_mm}mm {weight_kg}kg {application} {grade} {notes}
```

価格・数量・顧客名・日付はEmbedding対象に含めない（検索精度のノイズになるため）。
これらはpayloadにのみ格納し、検索結果の表示やフィルタリングに使用する。

### データ更新ルール

| 操作     | 条件                        | Qdrant処理                   |
| -------- | --------------------------- | ---------------------------- |
| 新規登録 | CSVのIDがQdrantに存在しない | upsert (新規)                |
| 更新     | CSVのIDがQdrantに存在する   | upsert (上書き)              |
| 削除     | -                           | Qdrant Dashboardから手動操作 |

- CSVにないIDのデータは影響を受けない（既存データは残る）
- Qdrantが正のデータ（マスタCSVの管理は不要）

---

## 4. データ取り込み

### 取り込み方式: Mattermost経由CSVアップロード

```
管理者: @見積 インポート  ← CSVファイルを添付して投稿

ボット: 「取り込み中... (150件処理中)」

ボット: 「取り込み完了
        新規登録: 145件
        更新: 3件
        エラー: 2件 (行3: materialが未入力, 行8: priceが数値でない)
        現在の総データ件数: 1,523件」
```

### 取り込みフロー

```
1. Mattermost Outgoing Webhookでリクエスト受信
2. メッセージから「インポート」コマンドを判定
3. file_ids を取得
4. Mattermost API (GET /files/{file_id}) でファイルダウンロード
5. ファイルをパース (CSV or Excel)
6. バリデーション (必須項目チェック、型チェック)
   → エラーがあれば行番号付きでレポート
7. 各行をテキスト化
8. Gemini Embedding API でベクトル化
   - バッチサイズ: 最大100件ずつ
   - レートリミット対応: 429エラー時は指数バックオフでリトライ（最大3回）
9. Qdrant に upsert (差分更新)
10. 取り込み結果をIncoming WebhookでMattermostに返信
```

### CSV仕様

```csv
id,name,material,diameter_mm,length_mm,weight_kg,application,grade,price,quantity,unit_price,customer,notes,estimate_date
1001,回転シャフト,SUS304,50,200,3.1,ポンプ用回転軸,精密級,45000,10,4500,A社,表面処理バフ仕上げ,2024-06-15
1002,固定ピン,S45C,10,80,0.05,治具用位置決め,一般,500,100,5,B社,,2024-07-01
```

- 文字コード: UTF-8 (BOMあり/なし両対応)
- ヘッダー行: 必須
- 必須列: id, name, material, diameter_mm, length_mm, application, price

### Excel仕様

- `.xlsx` 形式のみ対応
- 1行目をヘッダーとして扱う
- 列名はCSVと同一
- 1シート目のみ読み取り

---

## 5. RAGパイプライン

### 検索フロー

```
1. クエリ受信
   「SUS304でΦ30くらいのピン、だいたいいくら？」

2. クエリをEmbedding化
   Gemini text-embedding-004 → 768次元ベクトル

3. Qdrantでベクトル類似検索
   - 上位5件を取得
   - オプション: メタデータフィルタで絞り込み
     例: material = "SUS304" のみに限定

4. コンテキスト構築
   検索結果をプロンプトに組み込む

5. Gemini APIで回答生成
   システムプロンプト + 検索結果 + ユーザー質問 → 回答
```

### プロンプト設計

```
[システムプロンプト]
あなたは製造業の見積アシスタントです。
過去の見積データを参考に、ユーザーの問い合わせに対して概算見積を提示してください。

ルール:
- 過去の類似データを根拠として提示すること
- 確実な金額ではなく「目安」であることを明記すること
- 類似データがない場合は「該当するデータが見つかりませんでした」と回答すること
- 金額は根拠となるデータの範囲を示すこと（例: 3,000〜5,000円）

[検索結果]
以下は過去の見積データから類似する案件を検索した結果です:

1. 固定ピン S45C Φ10×80mm 0.05kg 治具用位置決め 一般 単価5円
2. ガイドピン SUS304 Φ20×100mm 0.25kg 金型用ガイド 精密級 単価850円
3. ...

[ユーザーの質問]
SUS304でΦ30くらいのピン、だいたいいくら？
```

### メタデータフィルタリング

ユーザーの入力からLLMで条件を抽出し、Qdrantのフィルタに変換する:

```python
# LLMが抽出した条件の例
filters = {
    "material": "SUS304",       # 完全一致
    "diameter_mm": {"gte": 25, "lte": 35},  # 範囲指定
}
```

これによりベクトル検索の精度を向上させる（ハイブリッド検索）。

---

## 6. Mattermost連携

### Outgoing Webhook設定

| 設定項目         | 値                                                |
| ---------------- | ------------------------------------------------- |
| 表示名           | 見積ボット                                        |
| トリガーワード   | `@見積` または `@estimate`                    |
| コールバックURL  | `http://rag-api:8000/api/v1/webhook/mattermost` |
| コンテンツタイプ | `application/json`                              |
| チャンネル       | 指定チャンネルまたは全チャンネル                  |

### Incoming Webhook設定

| 設定項目   | 値                                       |
| ---------- | ---------------------------------------- |
| 表示名     | 見積ボット                               |
| アイコン   | (任意)                                   |
| チャンネル | デフォルトチャンネル（投稿時に上書き可） |

### Bot Account設定

CSVファイルのダウンロードにMattermost APIを使用するため、Bot Accountが必要。

| 設定項目       | 値                                 |
| -------------- | ---------------------------------- |
| Bot ユーザー名 | `estimate-bot`                   |
| 必要な権限     | ファイル読み取り                   |
| トークン       | Personal Access Token or Bot Token |

### Mattermostコマンド一覧

| コマンド                       | 動作                         |
| ------------------------------ | ---------------------------- |
| `@見積 <自然言語の質問>`     | 類似見積を検索して概算を回答 |
| `@見積 インポート` + CSV添付 | CSVデータを差分取り込み      |
| `@見積 件数`                 | 現在の登録データ件数を表示   |

### メッセージフォーマット

#### 検索の入力例

```
@見積 SUS304 Φ50×200のシャフト、ポンプ用で精密級だといくらくらい？
```

#### 検索の回答例

```
📋 見積検索結果

お問い合わせ: SUS304 Φ50×200 シャフト ポンプ用 精密級

■ 類似案件 (上位3件)
1. 回転シャフト SUS304 Φ50×200mm | 単価 4,500円 (10個) | ポンプ用回転軸
2. 駆動シャフト SUS304 Φ45×250mm | 単価 5,200円 (5個) | 送風機用
3. 支持シャフト SUS316 Φ50×180mm | 単価 5,800円 (3個) | 薬液ポンプ用

■ 概算目安
4,500〜5,500円/個 程度

■ 補足
- 最も条件が近い案件1は2024年6月の見積です
- 数量によって単価が変動します
- 正式見積は別途ご確認ください

⚠️ この金額は過去データに基づく概算です。正式な見積ではありません。
```

#### インポートの回答例

```
📥 データ取り込み完了

新規登録: 45件
更新: 3件
エラー: 2件
  - 行3: materialが未入力
  - 行8: priceが数値でない

現在の総データ件数: 1,523件
```

---

## 7. データ管理 (Qdrant Dashboard)

### 概要

データの一覧確認・詳細表示・修正・削除は Qdrant Dashboard (標準付属のWeb管理画面) で行う。

### アクセス方法

Caddy経由でBasic認証付きで公開する（管理者のみアクセス可能）。

```
https://qdrant-admin.example.com → Qdrant Dashboard
```

### Caddy設定

```
qdrant-admin.example.com {
    basicauth {
        admin $2a$14$...   # bcryptハッシュ化したパスワード
    }
    reverse_proxy qdrant:6333
}
```

### Dashboardで可能な操作

| 操作     | 説明                                 |
| -------- | ------------------------------------ |
| 一覧表示 | 全データをページネーション付きで閲覧 |
| 検索     | ベクトル検索・フィルタ検索           |
| 詳細表示 | 個別レコードのpayload確認            |
| 編集     | payloadの値を直接修正                |
| 削除     | 個別レコードの削除                   |

※ Dashboardからpayloadを修正した場合、Embedding対象フィールド（名称・材質・サイズ等）を変更してもベクトルは自動再計算されない。ベクトルに影響する修正が必要な場合はCSVで再インポートする。

---

## 8. API設計

### ベースURL

```
http://rag-api:8000/api/v1
```

### エンドポイント一覧

#### POST `/webhook/mattermost`

Mattermost Outgoing Webhookからのリクエストを受信。メッセージ内容に応じて検索またはインポートを実行。

| パラメータ | 説明                           |
| ---------- | ------------------------------ |
| token      | Outgoing Webhookの検証トークン |
| text       | ユーザーの投稿テキスト         |
| channel_id | チャンネルID                   |
| user_name  | 投稿者名                       |
| file_ids   | 添付ファイルID（インポート時） |

コマンド判定ロジック:

- `インポート` を含む + file_ids あり → CSV取り込み処理
- `件数` を含む → データ件数を返信
- それ以外 → RAG検索処理

レスポンス: 即座に `{"text": "検索中..."}` を返す（Outgoing Webhookの直接レスポンス）。
最終的な回答はIncoming Webhook経由で非同期投稿する。

---

#### GET `/data/search`

デバッグ・管理用の直接検索API。

| パラメータ | 説明                     |
| ---------- | ------------------------ |
| q          | 検索クエリ (テキスト)    |
| material   | 材質フィルタ (任意)      |
| limit      | 取得件数 (デフォルト: 5) |

レスポンス:

```json
{
  "results": [
    {
      "id": 1001,
      "score": 0.92,
      "name": "回転シャフト",
      "material": "SUS304",
      "diameter_mm": 50.0,
      "length_mm": 200.0,
      "price": 45000,
      "unit_price": 4500,
      "quantity": 10
    }
  ]
}
```

---

#### GET `/data/count`

登録データ件数を取得。

レスポンス:

```json
{
  "count": 1523
}
```

---

#### GET `/health`

ヘルスチェック。

レスポンス:

```json
{
  "status": "ok",
  "qdrant": "connected",
  "gemini": "available"
}
```

---

## 9. デプロイ構成

### Docker Compose

```yaml
services:
  rag-api:
    build: ./rag-api
    expose:
      - "8000"
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - MATTERMOST_API_URL=${MATTERMOST_API_URL}
      - MATTERMOST_BOT_TOKEN=${MATTERMOST_BOT_TOKEN}
      - MATTERMOST_INCOMING_WEBHOOK_URL=${MATTERMOST_INCOMING_WEBHOOK_URL}
      - MATTERMOST_OUTGOING_WEBHOOK_TOKEN=${MATTERMOST_OUTGOING_WEBHOOK_TOKEN}
    depends_on:
      - qdrant
    networks:
      - caddy_net
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    expose:
      - "6333"
    networks:
      - caddy_net
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

networks:
  caddy_net:
    external: true

volumes:
  qdrant_data:
```

### ネットワーク構成

```
caddy_net (既存の外部ネットワーク、全サービス共有)
├── Caddy              ← 443で外部公開 (既存)
├── Mattermost         ← (既存)
├── Jitsi              ← (既存)
├── MeshCentral        ← (予定)
├── rag-api            ← Mattermost → rag-api:8000 (内部通信)
└── qdrant             ← rag-api → qdrant:6333 (内部通信)
                         Caddy → qdrant:6333 (Dashboard用)
```

- 全サービスが `caddy_net` に所属（ネットワークは1つのみ）
- Mattermost → rag-api はDocker内部通信（Caddy不要）
- Qdrant DashboardのみCaddy経由でBasic認証付き外部公開
- 外部公開ポートは一切なし（Caddyが443でSSL終端）

### Caddy設定 (既存Caddyfileに追記)

```
# Qdrant Dashboard (管理者用、Basic認証付き)
qdrant-admin.example.com {
    basicauth {
        admin $2a$14$...
    }
    reverse_proxy qdrant:6333
}
```

※ rag-apiはMattermostからDocker内部通信で直接アクセスするため、Caddyへの登録は不要。

### 環境変数 (.env)

```env
GEMINI_API_KEY=your-gemini-api-key
MATTERMOST_API_URL=https://mattermost.example.com/api/v4
MATTERMOST_BOT_TOKEN=your-bot-token
MATTERMOST_INCOMING_WEBHOOK_URL=https://mattermost.example.com/hooks/xxx
MATTERMOST_OUTGOING_WEBHOOK_TOKEN=xxx
```

### リソース目安

| コンテナ       | メモリ               | CPU             | ディスク         | 備考                    |
| -------------- | -------------------- | --------------- | ---------------- | ----------------------- |
| rag-api        | 256MB〜512MB         | 1コア           | 最小限           | Pythonアプリ            |
| qdrant         | 512MB〜1GB           | 1コア           | 1GB〜            | データ量1万件以下の場合 |
| **合計**           | **約1〜1.5GB**           | **2コア**           | **1〜2GB**           | 既存VPSに追加する分     |

- 見積データ1万件以下であれば最小構成のVPSで十分
- ボトルネックはGemini APIの呼び出し速度（特にデータ取り込み時）

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### ディレクトリ構成

```
estimate-rag/
├── docker-compose.yml
├── .env
└── rag-api/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py              # FastAPIアプリケーション (uvicornで起動)
    ├── config.py             # 設定管理
    ├── routers/
    │   ├── webhook.py        # Mattermost Webhook処理 (検索+インポート)
    │   └── search.py         # デバッグ用検索API
    ├── services/
    │   ├── rag.py            # RAGパイプライン
    │   ├── embedding.py      # Gemini Embedding呼び出し
    │   ├── llm.py            # Gemini LLM呼び出し
    │   ├── qdrant.py         # Qdrantクライアント
    │   ├── mattermost.py     # Mattermost API (ファイルDL、投稿)
    │   └── parser.py         # CSV/Excelパーサー
    ├── models/
    │   └── estimate.py       # データモデル定義
    └── prompts/
        └── system.txt        # システムプロンプト
```

---

## 10. 技術スタック

| カテゴリ          | ライブラリ    | バージョン | 用途                        |
| ----------------- | ------------- | ---------- | --------------------------- |
| Webフレームワーク | FastAPI       | 0.115+     | APIサーバー                 |
| ASGI              | uvicorn       | 0.32+      | FastAPI実行                 |
| LLM/Embedding     | google-genai  | 1.0+       | Gemini API呼び出し          |
| ベクトルDB        | qdrant-client | 1.12+      | Qdrant操作                  |
| CSV処理           | pandas        | 2.2+       | CSV/Excel読み込み           |
| Excel処理         | openpyxl      | 3.1+       | xlsxファイル対応            |
| バリデーション    | pydantic      | 2.0+       | データバリデーション        |
| HTTP              | httpx         | 0.28+      | Mattermost API・Webhook送信 |

---

## 11. 開発フェーズ

### Phase 1: 基盤構築 + RAG検索

- Docker Compose環境構築 (Qdrant + FastAPI)
- CSV取り込み処理の実装 (APIエンドポイント経由)
- Gemini Embedding + Qdrantへの格納
- ベクトル検索 + Geminiによる回答生成
- **ゴール: curlでCSV取り込みと類似見積検索ができる**

### Phase 2: Mattermost連携

- Outgoing/Incoming Webhook設定
- Bot Account作成
- Webhookハンドラ実装 (検索 + インポート)
- Mattermost API経由のファイルダウンロード実装
- メッセージフォーマット整備
- **ゴール: Mattermostから `@見積` で検索・インポートできる**

### Phase 3: 精度改善 + 管理機能

- メタデータフィルタリング（材質・サイズ範囲）
- プロンプトチューニング
- 検索結果のスコアリング調整
- Qdrant Dashboard をCaddy経由でBasic認証付き公開
- **ゴール: 実用的な精度 + 管理者がデータを確認・修正できる**

### Phase 4: 運用安定化

- エラーハンドリング強化
- ログ出力
- Qdrantデータのバックアップ運用
- **ゴール: 日常的に安定運用できる**
