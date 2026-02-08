import logging

from models.estimate import EstimateRecord, ImportResult
from services import embedding, llm, qdrant
from services.filter import extract_filters

logger = logging.getLogger(__name__)


async def search(query: str, limit: int = 5) -> dict:
    """クエリテキストで類似検索し、LLMで回答を生成する。"""
    query_vector = await embedding.embed_text(query)
    query_filter = await extract_filters(query)
    logger.info("Extracted filter: %s", query_filter)
    results = qdrant.search(query_vector, limit=limit, query_filter=query_filter)

    # フィルタ付きで結果が少ない場合、フィルタなしで再検索
    if len(results) < 2 and query_filter is not None:
        logger.info("Too few results with filter, retrying without filter")
        results = qdrant.search(query_vector, limit=limit)

    if not results:
        return {
            "results": [],
            "answer": "該当するデータが見つかりませんでした。",
        }

    context = _build_context(results)
    answer = await llm.generate_answer(query, context)

    return {
        "results": results,
        "answer": answer,
    }


async def import_records(records: list[EstimateRecord]) -> ImportResult:
    """レコードリストをEmbedding化してQdrantにupsertする。"""
    result = ImportResult()

    # 既存IDチェック
    for record in records:
        if qdrant.point_exists(record.id):
            result.updated_count += 1
        else:
            result.new_count += 1

    # Embedding生成
    texts = [r.to_embedding_text() for r in records]
    vectors = await embedding.embed_texts(texts)

    # Qdrant upsert
    ids = [r.id for r in records]
    payloads = [r.to_payload() for r in records]
    qdrant.upsert_points(ids, vectors, payloads)

    result.total_count = qdrant.count()
    return result


def _build_context(results: list[dict]) -> str:
    """検索結果をLLMプロンプト用のテキストに変換する。"""
    lines = []
    for i, r in enumerate(results, 1):
        parts = [
            r.get("name", ""),
            r.get("material", ""),
            f"Φ{r.get('diameter_mm', '')}×{r.get('length_mm', '')}mm",
        ]
        if r.get("weight_kg"):
            parts.append(f"{r['weight_kg']}kg")
        parts.append(r.get("application", ""))
        if r.get("grade"):
            parts.append(r["grade"])
        if r.get("unit_price"):
            parts.append(f"単価{r['unit_price']:,}円")
        elif r.get("price"):
            parts.append(f"{r['price']:,}円")
        if r.get("notes"):
            parts.append(r["notes"])
        lines.append(f"{i}. {' '.join(str(p) for p in parts)}")
    return "\n".join(lines)
