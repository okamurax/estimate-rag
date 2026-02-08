import asyncio
import logging

from fastapi import APIRouter, Request

from services import rag, qdrant, mattermost, parser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")


@router.post("/webhook/mattermost")
async def mattermost_webhook(request: Request):
    """Mattermost Outgoing Webhookからのリクエストを処理する。"""
    body = await request.json()
    text = body.get("text", "")
    channel_id = body.get("channel_id", "")
    file_ids = body.get("file_ids") or []

    # トリガーワードを除去
    query = text
    for trigger in ["@見積", "@estimate"]:
        query = query.replace(trigger, "").strip()

    # コマンド判定
    if "インポート" in query and file_ids:
        asyncio.create_task(_handle_import(channel_id, file_ids))
        return {"text": "📥 取り込み中..."}

    if "件数" in query:
        total = qdrant.count()
        return {"text": f"📊 現在の登録データ件数: {total:,}件"}

    # RAG検索
    asyncio.create_task(_handle_search(channel_id, query))
    return {"text": "🔍 検索中..."}


async def _handle_search(channel_id: str, query: str) -> None:
    """RAG検索を実行し、結果をMattermostに投稿する。"""
    try:
        logger.info("Search request: %s", query)
        result = await rag.search(query)
        answer = _format_search_response(query, result)
        logger.info("Search completed: %d results", len(result.get("results", [])))
    except Exception as e:
        logger.exception("Search failed for query: %s", query)
        answer = f"⚠️ 検索中にエラーが発生しました: {e}"
    await mattermost.post_message(channel_id, answer)


async def _handle_import(channel_id: str, file_ids: list[str]) -> None:
    """CSVインポートを実行し、結果をMattermostに投稿する。"""
    all_new = 0
    all_updated = 0
    all_errors: list[str] = []

    try:
        for file_id in file_ids:
            logger.info("Importing file: %s", file_id)
            content, filename = await mattermost.download_file(file_id)
            records, parse_errors = parser.parse_file(content, filename)
            all_errors.extend(parse_errors)

            if records:
                logger.info("Parsed %d records from %s", len(records), filename)
                result = await rag.import_records(records)
                all_new += result.new_count
                all_updated += result.updated_count
                all_errors.extend(result.errors)

        total = qdrant.count()
        logger.info("Import complete: new=%d, updated=%d, errors=%d", all_new, all_updated, len(all_errors))
        answer = _format_import_response(all_new, all_updated, all_errors, total)
    except Exception as e:
        logger.exception("Import failed")
        answer = f"⚠️ 取り込み中にエラーが発生しました: {e}"

    await mattermost.post_message(channel_id, answer)


def _format_search_response(query: str, result: dict) -> str:
    """検索結果をMattermost向けメッセージにフォーマットする。"""
    lines = [f"📋 **見積検索結果**\n"]
    lines.append(f"お問い合わせ: {query}\n")

    results = result.get("results", [])
    if results:
        lines.append("**■ 類似案件**")
        for i, r in enumerate(results, 1):
            name = r.get("name", "")
            material = r.get("material", "")
            d = r.get("diameter_mm", "")
            l = r.get("length_mm", "")
            unit_price = r.get("unit_price")
            price = r.get("price", 0)
            qty = r.get("quantity")
            app = r.get("application", "")

            price_str = f"単価 {unit_price:,}円 ({qty}個)" if unit_price and qty else f"{price:,}円"
            lines.append(f"{i}. {name} {material} Φ{d}×{l}mm | {price_str} | {app}")
        lines.append("")

    answer = result.get("answer", "")
    if answer:
        lines.append(f"**■ 概算目安**\n{answer}")

    lines.append("\n⚠️ この金額は過去データに基づく概算です。正式な見積ではありません。")
    return "\n".join(lines)


def _format_import_response(
    new: int, updated: int, errors: list[str], total: int
) -> str:
    """インポート結果をMattermost向けメッセージにフォーマットする。"""
    lines = ["📥 **データ取り込み完了**\n"]
    lines.append(f"新規登録: {new}件")
    lines.append(f"更新: {updated}件")

    if errors:
        lines.append(f"エラー: {len(errors)}件")
        for err in errors[:10]:  # 最大10件表示
            lines.append(f"  - {err}")
        if len(errors) > 10:
            lines.append(f"  - ... 他{len(errors) - 10}件")
    else:
        lines.append("エラー: 0件")

    lines.append(f"\n現在の総データ件数: {total:,}件")
    return "\n".join(lines)
