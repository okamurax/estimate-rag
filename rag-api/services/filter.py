import asyncio
import json

from google import genai
from google.genai.types import GenerateContentConfig
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

import config

_client = genai.Client(api_key=config.GEMINI_API_KEY)

_EXTRACTION_PROMPT = """\
ユーザーの問い合わせから、以下の検索条件を抽出してJSON形式で返してください。
該当しないフィールドはnullにしてください。

抽出対象:
- material: 材質（例: "SUS304", "S45C"）。完全一致用。
- diameter_min: 外径の下限 (mm)。数値のみ。
- diameter_max: 外径の上限 (mm)。数値のみ。
- length_min: 長さの下限 (mm)。数値のみ。
- length_max: 長さの上限 (mm)。数値のみ。

「Φ30くらい」のような曖昧な表現は ±20% の範囲に変換してください（例: 24〜36）。
「Φ50×200」のような正確な値はmin/maxを同じ値にしてください。

JSON以外のテキストは出力しないでください。

ユーザーの問い合わせ:
"""


async def extract_filters(query: str) -> Filter | None:
    """ユーザーのクエリからQdrantフィルタ条件を抽出する。"""
    try:
        response = await asyncio.to_thread(
            _client.models.generate_content,
            model=config.LLM_MODEL,
            contents=_EXTRACTION_PROMPT + query,
            config=GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        raw = json.loads(response.text)
    except Exception:
        return None

    conditions = []

    if raw.get("material"):
        conditions.append(
            FieldCondition(key="material", match=MatchValue(value=raw["material"]))
        )

    if raw.get("diameter_min") is not None or raw.get("diameter_max") is not None:
        conditions.append(
            FieldCondition(
                key="diameter_mm",
                range=Range(
                    gte=raw.get("diameter_min"),
                    lte=raw.get("diameter_max"),
                ),
            )
        )

    if raw.get("length_min") is not None or raw.get("length_max") is not None:
        conditions.append(
            FieldCondition(
                key="length_mm",
                range=Range(
                    gte=raw.get("length_min"),
                    lte=raw.get("length_max"),
                ),
            )
        )

    if not conditions:
        return None

    return Filter(must=conditions)
