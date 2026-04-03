from __future__ import annotations
import asyncio
import io
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.types import (
    BufferedInputFile, CallbackQuery, ChatMemberUpdated,
    InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

from core.adapter import BaseAdapter
from core.media import to_mp3, to_mp4
from core.message import UniversalMessage
from db import database as db

logger = logging.getLogger(__name__)


class TelegramAdapter(BaseAdapter):
    platform = "telegram"

    def __init__(self, token: str, owner_id: int, bus) -> None:
        self._bot      = Bot(token=token)
        self._dp       = Dispatcher()
        self._owner_id = owner_id
        self._bus      = bus

    def _is_admin(self, user_id: int) -> bool:
        return user_id == self._owner_id or db.is_admin("telegram", str(user_id))

    async def start(self) -> None:
        self._register_handlers()
        asyncio.create_task(self._dp.start_polling(self._bot))
        logger.info("Telegram adapter started")

    def _register_handlers(self) -> None:
        dp  = self._dp
        bot = self._bot

        @dp.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
        async def bot_joined(event: ChatMemberUpdated) -> None:
            chat = event.chat
            if chat.type not in ("channel", "supergroup", "group"):
                return
            db.upsert_chat("telegram", str(chat.id), chat.title or str(chat.id))
            logger.info("TG: joined channel %s (%s)", chat.title, chat.id)
            try:
                await bot.send_message(
                    self._owner_id,
                    f"✅ TG канал зарегистрирован: {chat.title} ({chat.id})",
                )
            except Exception:
                pass

        @dp.message(Command("start"))
        async def cmd_start(message: Message) -> None:
            if not self._is_admin(message.from_user.id):
                return
            await message.answer(
                "Мост Max ↔ TG ↔ Discord\n\n"
                "/routes — все маршруты\n"
                "/addroute — добавить маршрут\n"
                "/delroute — удалить маршрут\n"
                "/setchat — целевой чат для ЛС\n"
                "/admins — список админов\n"
            )

        @dp.message(Command("routes"))
        async def cmd_routes(message: Message) -> None:
            if not self._is_admin(message.from_user.id):
                return
            rows = db.get_all_routes()
            if not rows:
                await message.answer("Маршрутов нет.")
                return
            lines = [
                f"{r['id']}. {r['source_platform']}/"
                f"{r['source_title'] or r['source_chat_id']} → "
                f"{r['sink_platform']}/"
                f"{r['sink_title'] or r['sink_chat_id']}"
                for r in rows
            ]
            await message.answer("Маршруты:\n\n" + "\n".join(lines))

        @dp.message(Command("addroute"))
        async def cmd_addroute(message: Message) -> None:
            if not self._is_admin(message.from_user.id):
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=p, callback_data=f"ar_src_plat:{p}")]
                for p in ("max", "telegram", "discord")
            ])
            await message.answer("Платформа-источник:", reply_markup=kb)

        @dp.callback_query(F.data.startswith("ar_src_plat:"))
        async def cb_src_plat(callback: CallbackQuery) -> None:
            if not self._is_admin(callback.from_user.id):
                await callback.answer()
                return
            platform = callback.data.split(":")[1]
            chats    = db.get_chats(platform)
            if not chats:
                await callback.message.edit_text(f"Нет чатов для {platform}.")
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{r['title']} ({r['chat_id']})",
                    callback_data=f"ar_src_chat:{platform}:{r['chat_id']}",
                )]
                for r in chats
            ])
            await callback.message.edit_text(f"Чат-источник ({platform}):", reply_markup=kb)
            await callback.answer()

        @dp.callback_query(F.data.startswith("ar_src_chat:"))
        async def cb_src_chat(callback: CallbackQuery) -> None:
            if not self._is_admin(callback.from_user.id):
                await callback.answer()
                return
            _, platform, chat_id = callback.data.split(":", 2)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=p,
                    callback_data=f"ar_snk_plat:{platform}:{chat_id}:{p}",
                )]
                for p in ("max", "telegram", "discord")
                if p != platform
            ])
            await callback.message.edit_text("Платформа-получатель:", reply_markup=kb)
            await callback.answer()

        @dp.callback_query(F.data.startswith("ar_snk_plat:"))
        async def cb_snk_plat(callback: CallbackQuery) -> None:
            if not self._is_admin(callback.from_user.id):
                await callback.answer()
                return
            _, src_plat, src_chat, snk_plat = callback.data.split(":", 3)
            chats = db.get_chats(snk_plat)
            if not chats:
                await callback.message.edit_text(f"Нет чатов для {snk_plat}.")
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{r['title']} ({r['chat_id']})",
                    callback_data=f"ar_snk_chat:{src_plat}:{src_chat}:{snk_plat}:{r['chat_id']}",
                )]
                for r in chats
            ])
            await callback.message.edit_text(f"Чат-получатель ({snk_plat}):", reply_markup=kb)
            await callback.answer()

        @dp.callback_query(F.data.startswith("ar_snk_chat:"))
        async def cb_snk_chat(callback: CallbackQuery) -> None:
            if not self._is_admin(callback.from_user.id):
                await callback.answer()
                return
            _, src_plat, src_chat, snk_plat, snk_chat = callback.data.split(":", 4)
            db.add_route(src_plat, src_chat, snk_plat, snk_chat)
            await callback.message.edit_text(
                f"✅ Маршрут добавлен:\n"
                f"{src_plat}/{src_chat} → {snk_plat}/{snk_chat}"
            )
            await callback.answer()

        @dp.message(Command("delroute"))
        async def cmd_delroute(message: Message) -> None:
            if not self._is_admin(message.from_user.id):
                return
            rows = db.get_all_routes()
            if not rows:
                await message.answer("Маршрутов нет.")
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"❌ {r['source_platform']}/{r['source_title'] or r['source_chat_id']}"
                         f" → {r['sink_platform']}/{r['sink_title'] or r['sink_chat_id']}",
                    callback_data=f"delroute:{r['id']}",
                )]
                for r in rows
            ])
            await message.answer("Выберите маршрут для удаления:", reply_markup=kb)

        @dp.callback_query(F.data.startswith("delroute:"))
        async def cb_delroute(callback: CallbackQuery) -> None:
            if not self._is_admin(callback.from_user.id):
                await callback.answer()
                return
            route_id = int(callback.data.split(":")[1])
            db.remove_route(route_id)
            await callback.message.edit_text("✅ Маршрут удалён.")
            await callback.answer()

        @dp.message(Command("setchat"))
        async def cmd_setchat(message: Message) -> None:
            if not self._is_admin(message.from_user.id):
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=p, callback_data=f"sc_plat:{p}")]
                for p in ("max", "telegram", "discord")
            ])
            await message.answer("Платформа для ЛС:", reply_markup=kb)

        @dp.callback_query(F.data.startswith("sc_plat:"))
        async def cb_sc_plat(callback: CallbackQuery) -> None:
            if not self._is_admin(callback.from_user.id):
                await callback.answer()
                return
            platform = callback.data.split(":")[1]
            chats    = db.get_chats(platform)
            if not chats:
                await callback.message.edit_text(f"Нет чатов для {platform}.")
                return
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{r['title']} ({r['chat_id']})",
                    callback_data=f"sc_chat:{platform}:{r['chat_id']}",
                )]
                for r in chats
            ])
            await callback.message.edit_text("Выберите чат:", reply_markup=kb)
            await callback.answer()

        @dp.callback_query(F.data.startswith("sc_chat:"))
        async def cb_sc_chat(callback: CallbackQuery) -> None:
            if not self._is_admin(callback.from_user.id):
                await callback.answer()
                return
            _, platform, chat_id = callback.data.split(":", 2)
            db.set_setting("ls_target_platform", platform)
            db.set_setting("ls_target_chat_id", chat_id)
            await callback.message.edit_text(f"✅ ЛС → {platform}/{chat_id}")
            await callback.answer()

        @dp.message(Command("admins"))
        async def cmd_admins(message: Message) -> None:
            if not self._is_admin(message.from_user.id):
                return
            admins = db.get_admins("telegram")
            if not admins:
                await message.answer("Дополнительных админов нет.\n(owner всегда имеет доступ)")
                return
            lines = "\n".join(f"• {uid}" for uid in admins)
            await message.answer(f"Админы Telegram:\n{lines}")

        @dp.message(
            F.chat.type == "private",
            F.voice | F.video_note | F.video | F.text | F.photo,
        )
        async def handle_ls(message: Message) -> None:
            platform = db.get_setting("ls_target_platform")
            chat_id  = db.get_setting("ls_target_chat_id")
            if not platform or not chat_id:
                if message.from_user.id == self._owner_id:
                    await message.answer("Целевой чат не задан. Используйте /setchat.")
                return
            universal = await self._build_universal(message)
            adapter   = self._bus._adapters.get(platform)
            if adapter:
                asyncio.create_task(adapter.send(universal, chat_id))

    async def _build_universal(self, message: Message) -> UniversalMessage:
        from core.identity import resolve_chat_title
        photo_bytes      = None
        audio_bytes      = None
        video_note_bytes = None
        media_url        = None

        if message.photo:
            photo_bytes = await self._download_tg_file(message.photo[-1].file_id)
            media_url   = f"tg://file/{message.photo[-1].file_id}"
        elif message.voice:
            raw = await self._download_tg_file(message.voice.file_id)
            if raw:
                audio_bytes = await to_mp3(raw, input_ext="ogg")
        elif message.video_note:
            raw = await self._download_tg_file(message.video_note.file_id)
            if raw:
                video_note_bytes = await to_mp4(raw, input_ext="mp4")
        elif message.video:
            raw = await self._download_tg_file(message.video.file_id)
            if raw:
                video_note_bytes = await to_mp4(raw, input_ext="mp4")

        user      = message.from_user
        user_name = None
        if user:
            parts     = [user.first_name or "", user.last_name or ""]
            user_name = " ".join(p for p in parts if p).strip() or user.username

        chat_title = resolve_chat_title("telegram", str(message.chat.id))

        return UniversalMessage(
            source_platform   = "telegram",
            source_chat_id    = str(message.chat.id),
            source_user_id    = str(message.from_user.id),
            source_user_name  = user_name,
            source_chat_title = chat_title,
            text              = message.text or message.caption or "",
            photo_bytes       = photo_bytes,
            audio_bytes       = audio_bytes,
            video_note_bytes  = video_note_bytes,
            media_url         = media_url,
            timestamp         = message.date,
        )

    async def send(self, msg: UniversalMessage, target_chat_id: str) -> bool:
        try:
            chat_id = int(target_chat_id)
            caption = self._format_caption(msg)

            if msg.photo_bytes:
                file = BufferedInputFile(msg.photo_bytes, filename="photo.jpg")
                await self._bot.send_photo(chat_id=chat_id, photo=file, caption=caption)
            elif msg.audio_bytes:
                file = BufferedInputFile(msg.audio_bytes, filename="voice.mp3")
                await self._bot.send_audio(chat_id=chat_id, audio=file, caption=caption)
            elif msg.video_note_bytes:
                file = BufferedInputFile(msg.video_note_bytes, filename="video.mp4")
                await self._bot.send_video(chat_id=chat_id, video=file, caption=caption)
            else:
                await self._bot.send_message(chat_id=chat_id, text=caption)

            return True
        except Exception:
            logger.exception("TG send failed")
            return False

    @staticmethod
    def _format_caption(msg: UniversalMessage) -> str:
        ts         = msg.timestamp.strftime("%d.%m.%Y %H:%M:%S")
        text       = msg.text or ""
        user_label = msg.source_user_name or msg.source_user_id
        chat_label = msg.source_chat_title or msg.source_chat_id
        return (
            f"🔀 {msg.source_platform} → telegram\n"
            f"👤 {user_label} | 💬 {chat_label}\n"
            f"🕐 {ts}" + (f"\n\n{text}" if text else "")
        )

    async def _download_tg_file(self, file_id: str) -> bytes | None:
        try:
            file = await self._bot.get_file(file_id)
            bio  = io.BytesIO()
            await self._bot.download_file(file.file_path, bio)
            return bio.getvalue()
        except Exception as e:
            logger.error("TG file download failed: %s", e)
            return None
