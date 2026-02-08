import httpx

import config


async def download_file(file_id: str) -> tuple[bytes, str]:
    """Mattermost APIからファイルをダウンロードする。(content, filename)を返す。"""
    async with httpx.AsyncClient() as client:
        # ファイル情報を取得
        info_resp = await client.get(
            f"{config.MATTERMOST_API_URL}/files/{file_id}/info",
            headers={"Authorization": f"Bearer {config.MATTERMOST_BOT_TOKEN}"},
        )
        info_resp.raise_for_status()
        filename = info_resp.json().get("name", "unknown.csv")

        # ファイル本体をダウンロード
        file_resp = await client.get(
            f"{config.MATTERMOST_API_URL}/files/{file_id}",
            headers={"Authorization": f"Bearer {config.MATTERMOST_BOT_TOKEN}"},
        )
        file_resp.raise_for_status()
        return file_resp.content, filename


async def post_message(channel_id: str, text: str) -> None:
    """Incoming Webhookでメッセージを投稿する。"""
    async with httpx.AsyncClient() as client:
        await client.post(
            config.MATTERMOST_INCOMING_WEBHOOK_URL,
            json={"channel_id": channel_id, "text": text},
        )
