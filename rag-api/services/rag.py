import logging

from qdrant_client.models import FieldCondition, Filter, MatchValue

from models.estimate import EstimateRecord, ImportResult
from services import embedding, llm, qdrant
from services.filter import extract_filters

logger = logging.getLogger(__name__)


async def search(query: str, limit: int = 5, material_filter: str | None = None) -> dict:
    """クエリテキストで類似検索し、LLMで回答を生成する。"""
    query_vector = await embedding.embed_text(query)
    query_filter = await extract_filters(query)

    # 明示的なmaterialパラメータがある場合、フィルタに追加/上書き
    if material_filter:
        material_cond = FieldCondition(key="material", match=MatchValue(value=material_filter))
        if query_filter and query_filter.must:
            # 既存のmaterial条件を除去して上書き
            query_filter.must = [c for c in query_filter.must if getattr(c, 'key', None) != 'material']
            query_filter.must.append(material_cond)
        else:
            query_filter = Filter(must=[material_cond])
    logger.info("Extracted filter: %s", query_filter)
    results = await qdrant.search(query_vector, limit=limit, query_filter=query_filter)

    # フィルタ付きで結果が少ない場合、フィルタなしで再検索
    if len(results) < 2 and query_filter is not None:
        logger.info("Too few results with filter, retrying without filter")
        results = await qdrant.search(query_vector, limit=limit)

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

    # 既存IDチェック（一括取得でN+1を回避）
    ids = [r.id for r in records]
    existing_ids = await qdrant.get_existing_ids(ids)
    result.updated_count = len(existing_ids)
    result.new_count = len(ids) - result.updated_count

    # Embedding生成
    texts = [r.to_embedding_text() for r in records]
    vectors = await embedding.embed_texts(texts)

    # Qdrant upsert
    payloads = [r.to_payload() for r in records]
    await qdrant.upsert_points(ids, vectors, payloads)

    result.total_count = await qdrant.count()
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
