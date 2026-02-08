from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    PointStruct,
    VectorParams,
)

import config

_client = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)


def ensure_collection() -> None:
    """コレクションが存在しなければ作成する。"""
    collections = [c.name for c in _client.get_collections().collections]
    if config.QDRANT_COLLECTION not in collections:
        _client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=config.EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )


def upsert_points(
    ids: list[int], vectors: list[list[float]], payloads: list[dict]
) -> None:
    """ポイントをupsertする。"""
    points = [
        PointStruct(id=id_, vector=vector, payload=payload)
        for id_, vector, payload in zip(ids, vectors, payloads)
    ]
    _client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)


def search(
    vector: list[float],
    limit: int = config.SEARCH_LIMIT,
    query_filter: Filter | None = None,
) -> list[dict]:
    """ベクトル類似検索を行い結果を返す。"""
    results = _client.query_points(
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


def count() -> int:
    """コレクション内のポイント数を返す。"""
    info = _client.get_collection(config.QDRANT_COLLECTION)
    return info.points_count


def point_exists(point_id: int) -> bool:
    """指定IDのポイントが存在するか確認する。"""
    try:
        results = _client.retrieve(
            collection_name=config.QDRANT_COLLECTION, ids=[point_id]
        )
        return len(results) > 0
    except Exception:
        return False


def is_healthy() -> bool:
    """Qdrantへの接続が正常か確認する。"""
    try:
        _client.get_collections()
        return True
    except Exception:
        return False
