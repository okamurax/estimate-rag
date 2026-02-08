import asyncio
from pathlib import Path

from google.genai.types import GenerateContentConfig

import config
from services.gemini_client import client as _client
_system_prompt = (Path(__file__).parent.parent / "prompts" / "system.txt").read_text(
    encoding="utf-8"
)


async def generate_answer(query: str, context: str) -> str:
    """検索結果コンテキストとユーザー質問からLLM回答を生成する。"""
    prompt = f"""[検索結果]
以下は過去の見積データから類似する案件を検索した結果です:

{context}

[ユーザーの質問]
{query}"""

    response = await asyncio.to_thread(
        _client.models.generate_content,
        model=config.LLM_MODEL,
        contents=prompt,
        config=GenerateContentConfig(system_instruction=_system_prompt),
    )
    return response.text
