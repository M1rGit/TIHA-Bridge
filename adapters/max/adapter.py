from __future__ import annotations
import asyncio
import logging
import os
import tempfile
from datetime import datetime

import httpx
from pymax import MaxClient
from pymax.files import File, Photo, Video

from core.adapter import BaseAdapter
from core.identity import resolve_chat_title
from core.media import to_mp3, to_mp4
from core.message import UniversalMessage
from db import database as db

logger = logging.getLogger(__name__)


class MaxAdapter(BaseAdapter):
    platform = "max"

    def __init__(self, client: MaxClient, bus) -> None:
        self._client = client
        self._bus    = bus

    async def start(self) -> None:
        @self._client.on_raw_receive
        async def handle_raw(data: dict) -> None:
            if data.get("opcode") != 128:
                return

            payload = data.get("payload", {})
            raw_msg = payload.get("message", {})
            chat_id = payload.get("chatId")

            if not raw_msg or not chat_id:
                return

            try:
                from pymax.types import Message
                msg = Message.from_dict(raw_msg)
            except Exception as e:
                logger.error("Max parse error: %s", e)
                return

            # Авторегистрация чата
            known = {r["chat_id"] for r in db.get_chats("max")}
            if str(chat_id) not in known:
                all_chats = self._client.chats + self._client.dialogs
                found     = next((c for c in all_chats if c.id == chat_id), None)
                title     = getattr(found, "title", None) or str(chat_id)
                db.upsert_chat("max", str(chat_id), title)

            attaches = raw_msg.get("attaches", [])

            # Фото
            photo_bytes = None
            media_url   = None
            photos = [a for a in attaches if a.get("_type") == "PHOTO" and a.get("baseUrl")]
            if photos:
                media_url   = photos[0]["baseUrl"]
                photo_bytes = await self._download_url(media_url)

            # Голосовое
            audio_bytes = None
            voices = [a for a in attaches if a.get("_type") in ("VOICE", "AUDIO") and a.get("baseUrl")]
            if voices:
                raw = await self._download_url(voices[0]["baseUrl"])
                if raw:
                    audio_bytes = await to_mp3(raw, input_ext="ogg")

            # Видео
            videos = [a for a in attaches if a.get("_type") == "VIDEO"]

            # Имя берём только из кеша БД — без сетевых запросов
            sender_id  = str(msg.sender) if msg.sender else ""
            user_name  = db.get_user_name("max", sender_id)
            chat_title = resolve_chat_title("max", str(chat_id))

            # Если имени нет в кеше — грузим в фоне для следующего раза
            if sender_id and not user_name:
                asyncio.create_task(
                    self._fetch_user_name_background(sender_id)
                )

            universal = UniversalMessage(
                source_platform   = "max",
                source_chat_id    = str(chat_id),
                source_user_id    = sender_id,
                source_user_name  = user_name,
                source_chat_title = chat_title,
                text              = msg.text or "",
                photo_bytes       = photo_bytes,
                audio_bytes       = audio_bytes,
                video_note_bytes  = None,
                media_url         = media_url,
                timestamp         = datetime.fromtimestamp(msg.time / 1000),
            )

            if videos:
                v = videos[0]
                asyncio.create_task(self._fetch_and_deliver_video(
                    universal=universal,
                    chat_id=chat_id,
                    message_id=int(raw_msg.get("id", 0)),
                    video_id=int(v.get("videoId", 0)),
                    token=v.get("token", ""),
                    thumbnail_url=v.get("thumbnail"),
                ))
            else:
                await self._bus.publish(universal)

        @self._client.on_start
        async def on_start() -> None:
            for chat in self._client.chats + self._client.dialogs:
                title = getattr(chat, "title", None) or str(chat.id)
                db.upsert_chat("max", str(chat.id), title)
            logger.info(
                "Max adapter started, %d chats registered",
                len(self._client.chats + self._client.dialogs),
            )

    async def _fetch_user_name_background(self, sender_id: str) -> None:
        """Грузит имя пользователя в фоне и кеширует в БД."""
        await asyncio.sleep(3)  # даём время recv loop успокоиться
        try:
            user = await self._client.get_user(int(sender_id))
            if user and user.names:
                n     = user.names[0]
                first = getattr(n, "first_name", "") or getattr(n, "first", "") or ""
                last  = getattr(n, "last_name", "")  or getattr(n, "last", "")  or ""
                name  = f"{first} {last}".strip()
                if name:
                    db.upsert_user_name("max", sender_id, name)
                    logger.debug("Cached user name: %s → %s", sender_id, name)
        except Exception as e:
            logger.debug("Background user fetch failed for %s: %s", sender_id, e)

    async def _fetch_and_deliver_video(
        self,
        universal: UniversalMessage,
        chat_id: int,
        message_id: int,
        video_id: int,
        token: str,
        thumbnail_url: str | None,
    ) -> None:
        await asyncio.sleep(2)
        try:
            video_request = await self._client.get_video_by_id(
                chat_id=chat_id,
                message_id=message_id,
                video_id=video_id,
            )
            url = None
            if video_request:
                for attr in ("url", "link", "download_url", "src"):
                    url = getattr(video_request, attr, None)
                    if url:
                        break

            if url:
                raw = await self._download_url(url)
                if raw:
                    converted = await to_mp4(raw, input_ext="mp4")
                    if converted:
                        universal.video_note_bytes = converted

            if not universal.video_note_bytes and thumbnail_url:
                logger.warning("No video source, sending thumbnail")
                universal.photo_bytes = await self._download_url(thumbnail_url)
                universal.media_url   = thumbnail_url

        except Exception as e:
            logger.error("Video fetch failed: %s", e)
            if thumbnail_url:
                universal.photo_bytes = await self._download_url(thumbnail_url)
                universal.media_url   = thumbnail_url

        await self._bus.publish(universal)

    async def send(self, msg: UniversalMessage, target_chat_id: str) -> bool:
        for _ in range(30):
            if self._client.is_connected:
                break
            await asyncio.sleep(1)
        else:
            logger.warning("Max not connected, skipping send")
            return False

        try:
            chat_id = int(target_chat_id)
            if chat_id == 0:
                logger.error("Invalid chat_id=0, skipping")
                return False

            if msg.photo_bytes:
                result = await self._send_with_tempfile(
                    msg, chat_id, msg.photo_bytes, ".jpg",
                    lambda path: Photo(path=path),
                )
            elif msg.audio_bytes:
                result = await self._send_with_tempfile(
                    msg, chat_id, msg.audio_bytes, ".mp3",
                    lambda path: File(path=path),
                )
            elif msg.video_note_bytes:
                result = await self._send_with_tempfile(
                    msg, chat_id, msg.video_note_bytes, ".mp4",
                    lambda path: Video(path=path),
                )
            else:
                result = await self._client.send_message(
                    text=msg.text, chat_id=chat_id, notify=True,
                )
            return result is not None

        except Exception:
            logger.exception("Max send failed")
            return False

    async def _send_with_tempfile(self, msg, chat_id, data, suffix, make_attach):
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            attachment = make_attach(tmp_path)
            return await self._client.send_message(
                text=msg.text, chat_id=chat_id, notify=True, attachment=attachment,
            )
        finally:
            os.unlink(tmp_path)

    @staticmethod
    async def _download_url(url: str) -> bytes | None:
        try:
            async with httpx.AsyncClient(timeout=30) as http:
                resp = await http.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.error("Download failed (%s): %s", url, e)
            return None
