from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    PointStruct,
    VectorParams,
)

import config

_client = AsyncQdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)

_UPSERT_BATCH_SIZE = 100


async def ensure_collection() -> None:
    """コレクションが存在しなければ作成する。"""
    collections = [c.name for c in (await _client.get_collections()).collections]
    if config.QDRANT_COLLECTION not in collections:
        await _client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=config.EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )


async def upsert_points(
    ids: list[int], vectors: list[list[float]], payloads: list[dict]
) -> None:
    """ポイントをバッチ分割してupsertする。"""
    for i in range(0, len(ids), _UPSERT_BATCH_SIZE):
        batch_ids = ids[i : i + _UPSERT_BATCH_SIZE]
        batch_vectors = vectors[i : i + _UPSERT_BATCH_SIZE]
        batch_payloads = payloads[i : i + _UPSERT_BATCH_SIZE]
        points = [
            PointStruct(id=id_, vector=vector, payload=payload)
            for id_, vector, payload in zip(batch_ids, batch_vectors, batch_payloads)
        ]
        await _client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)


async def search(
    vector: list[float],
    limit: int = config.SEARCH_LIMIT,
    query_filter: Filter | None = None,
) -> list[dict]:
    """ベクトル類似検索を行い結果を返す。"""
    results = await _client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )
    return [
        {"id": point.id, "score": point.score, **point.payload}
        for point in results.points
    ]


async def count() -> int:
    """コレクション内のポイント数を返す。"""
    info = await _client.get_collection(config.QDRANT_COLLECTION)
    return info.points_count


async def get_existing_ids(ids: list[int]) -> set[int]:
    """指定IDリストのうち、既にQdrantに存在するIDのセットを返す。"""
    try:
        results = await _client.retrieve(
            collection_name=config.QDRANT_COLLECTION, ids=ids
        )
        return {point.id for point in results}
    except Exception:
        return set()


async def is_healthy() -> bool:
    """Qdrantへの接続が正常か確認する。"""
    try:
        await _client.get_collections()
        return True
    except Exception:
        return False
