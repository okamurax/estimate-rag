import asyncio

import config
from services.gemini_client import client as _client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """テキストのリストをEmbeddingベクトルに変換する。バッチ処理+リトライ対応。"""
    all_vectors: list[list[float]] = []

    for i in range(0, len(texts), config.EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + config.EMBEDDING_BATCH_SIZE]
        vectors = await _embed_batch_with_retry(batch)
        all_vectors.extend(vectors)

    return all_vectors


async def embed_text(text: str) -> list[float]:
    """単一テキストをEmbeddingベクトルに変換する。"""
    result = await embed_texts([text])
    return result[0]


async def _embed_batch_with_retry(
    texts: list[str], max_retries: int = 3
) -> list[list[float]]:
    """バッチEmbedding。429エラー時は指数バックオフでリトライ。"""
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                _client.models.embed_content,
                model=config.EMBEDDING_MODEL,
                contents=texts,
            )
            return [e.values for e in response.embeddings]
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                await asyncio.sleep(wait)
                continue
            raise
