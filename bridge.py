import asyncio

# (max_chat_id, caption, photo_urls)
max_to_tg: asyncio.Queue[tuple[int, str, list[str]]] = asyncio.Queue()

# (max_chat_id, text, photo_bytes | None)
tg_to_max: asyncio.Queue[tuple[int, str, bytes | None]] = asyncio.Queue()
