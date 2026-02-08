from fastapi import APIRouter, UploadFile, File

from services import rag, qdrant, parser

router = APIRouter(prefix="/api/v1/data")


@router.get("/search")
async def search(q: str, limit: int = 5):
    """デバッグ・管理用の直接検索API。"""
    result = await rag.search(q, limit=limit)
    return result


@router.get("/count")
async def count():
    """登録データ件数を取得。"""
    return {"count": qdrant.count()}


@router.post("/import")
async def import_csv(file: UploadFile = File(...)):
    """デバッグ用: CSVファイルを直接アップロードして取り込む。"""
    content = await file.read()
    records, errors = parser.parse_file(content, file.filename or "upload.csv")

    if not records and errors:
        return {"status": "error", "errors": errors}

    result = await rag.import_records(records)
    return {
        "status": "ok",
        "new_count": result.new_count,
        "updated_count": result.updated_count,
        "errors": errors + result.errors,
        "total_count": result.total_count,
    }
