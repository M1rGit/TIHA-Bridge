import asyncio
import io
from collections.abc import Callable
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ChatMemberUpdated,
)
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION
from pymax.files import Photo
import bridge
import db


def _max_chats_keyboard() -> InlineKeyboardMarkup:
    chats = db.get_max_chats()
    if not chats:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💬 {row['title']} ({row['chat_id']})",
            callback_data=f"link_max:{row['chat_id']}",
        )]
        for row in chats
    ])


def _tg_channels_keyboard(max_chat_id: int) -> InlineKeyboardMarkup:
    channels = db.get_tg_channels()
    if not channels:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📢 {row['title']} ({row['channel_id']})",
            callback_data=f"link_tg:{max_chat_id}:{row['channel_id']}",
        )]
        for row in channels
    ])


def _setchat_keyboard() -> InlineKeyboardMarkup:
    chats = db.get_max_chats()
    if not chats:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💬 {row['title']} ({row['chat_id']})",
            callback_data=f"setchat:{row['chat_id']}",
        )]
        for row in chats
    ])


async def _download_tg_photo(bot: Bot, message: Message) -> bytes | None:
    """Скачивает фото из TG сообщения и возвращает bytes."""
    try:
        photo  = message.photo[-1]  # берём максимальное разрешение
        file   = await bot.get_file(photo.file_id)
        bio    = io.BytesIO()
        await bot.download_file(file.file_path, bio)
        return bio.getvalue()
    except Exception as e:
        print(f"[TG→Max][ОШИБКА СКАЧИВАНИЯ ФОТО] {e}")
        return None


async def _send_to_max(
    bot: Bot,
    message: Message,
    target_chat_id: int,
    sender_id: int,
) -> None:
    """Универсальная отправка текста или фото из TG в Max."""
    # Кладём в очередь как (chat_id, text, photo_bytes | None)
    if message.photo:
        photo_bytes = await _download_tg_photo(bot, message)
        caption     = message.caption or ""
        await bridge.tg_to_max.put((target_chat_id, caption, photo_bytes))
    else:
        await bridge.tg_to_max.put((target_chat_id, message.text or "", None))

    db.log_message(
        direction    = "tg_to_max",
        sender_id    = sender_id,
        recipient_id = target_chat_id,
        chat_id      = target_chat_id,
        text         = message.text or message.caption or "<фото>",
    )


def create_bot(token: str, user_id: int) -> tuple[Bot, Dispatcher, Callable]:
    bot = Bot(token=token)
    dp  = Dispatcher()

    # --- TG бот добавлен в канал → сохраняем в БД ---
    @dp.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
    async def bot_added_to_channel(event: ChatMemberUpdated) -> None:
        chat = event.chat
        if chat.type not in ("channel", "supergroup", "group"):
            return
        db.upsert_tg_channel(chat.id, chat.title or str(chat.id))
        print(f"[TG] Бот добавлен в канал: {chat.title} ({chat.id})")
        try:
            await bot.send_message(
                user_id,
                f"✅ TG канал зарегистрирован:\n{chat.title} ({chat.id})",
            )
        except Exception:
            pass

    # --- /start ---
    @dp.message(Command("start"), F.from_user.id == user_id)
    async def cmd_start(message: Message) -> None:
        target_id   = db.get_ls_target_chat()
        rows        = db.get_max_chats()
        name        = next((r["title"] for r in rows if r["chat_id"] == target_id), "не задан")
        await message.answer(
            "Мост Max ↔ TG\n\n"
            "/link — связать Max группу с TG каналом\n"
            "/links — показать все связки\n"
            "/unlink — удалить связку\n"
            f"/setchat — выбрать чат Max для ЛС (сейчас: {name})"
        )

    # --- /setchat ---
    @dp.message(Command("setchat"), F.from_user.id == user_id)
    async def cmd_setchat(message: Message) -> None:
        kb = _setchat_keyboard()
        if not kb.inline_keyboard:
            await message.answer("Нет зарегистрированных Max чатов.")
            return
        await message.answer("Выберите Max чат для пересылки сообщений из ЛС:", reply_markup=kb)

    @dp.callback_query(F.data.startswith("setchat:"), F.from_user.id == user_id)
    async def cb_setchat(callback: CallbackQuery) -> None:
        chat_id = int(callback.data.split(":")[1])
        db.set_ls_target_chat(chat_id)
        rows  = db.get_max_chats()
        title = next((r["title"] for r in rows if r["chat_id"] == chat_id), str(chat_id))
        await callback.message.edit_text(f"✅ Сообщения из ЛС будут идти в: {title}")
        await callback.answer()

    # --- /link шаг 1 ---
    @dp.message(Command("link"), F.from_user.id == user_id)
    async def cmd_link(message: Message) -> None:
        kb = _max_chats_keyboard()
        if not kb.inline_keyboard:
            await message.answer("Нет зарегистрированных Max групп.")
            return
        await message.answer("Выберите Max группу:", reply_markup=kb)

    # --- /link шаг 2 ---
    @dp.callback_query(F.data.startswith("link_max:"), F.from_user.id == user_id)
    async def cb_link_max(callback: CallbackQuery) -> None:
        max_chat_id = int(callback.data.split(":")[1])
        kb = _tg_channels_keyboard(max_chat_id)
        if not kb.inline_keyboard:
            await callback.message.edit_text("Нет зарегистрированных TG каналов.")
            return
        await callback.message.edit_text(
            f"Max группа: {max_chat_id}\nВыберите TG канал:",
            reply_markup=kb,
        )
        await callback.answer()

    # --- /link шаг 3 ---
    @dp.callback_query(F.data.startswith("link_tg:"), F.from_user.id == user_id)
    async def cb_link_tg(callback: CallbackQuery) -> None:
        _, max_chat_id, tg_channel_id = callback.data.split(":")
        max_chat_id   = int(max_chat_id)
        tg_channel_id = int(tg_channel_id)
        db.add_link(max_chat_id, tg_channel_id)
        chats    = {r["chat_id"]: r["title"] for r in db.get_max_chats()}
        channels = {r["channel_id"]: r["title"] for r in db.get_tg_channels()}
        await callback.message.edit_text(
            f"✅ Связка создана:\n"
            f"Max: {chats.get(max_chat_id, max_chat_id)}\n"
            f"TG:  {channels.get(tg_channel_id, tg_channel_id)}"
        )
        await callback.answer()

    # --- /links ---
    @dp.message(Command("links"), F.from_user.id == user_id)
    async def cmd_links(message: Message) -> None:
        links = db.get_all_links()
        if not links:
            await message.answer("Связок пока нет.")
            return
        text = "\n".join(
            f"💬 {r['max_title']} → 📢 {r['tg_title']}"
            for r in links
        )
        await message.answer(f"Активные связки:\n\n{text}")

    # --- /unlink ---
    @dp.message(Command("unlink"), F.from_user.id == user_id)
    async def cmd_unlink(message: Message) -> None:
        links = db.get_all_links()
        if not links:
            await message.answer("Связок нет.")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"❌ {r['max_title']} → {r['tg_title']}",
                callback_data=f"unlink:{r['chat_id']}",
            )]
            for r in links
        ])
        await message.answer("Выберите связку для удаления:", reply_markup=kb)

    @dp.callback_query(F.data.startswith("unlink:"), F.from_user.id == user_id)
    async def cb_unlink(callback: CallbackQuery) -> None:
        max_chat_id = int(callback.data.split(":")[1])
        db.remove_link(max_chat_id)
        await callback.message.edit_text("✅ Связка удалена.")
        await callback.answer()

    # --- ЛС от любого пользователя (текст или фото) → Max ---
    @dp.message(
        F.chat.type == "private",
        ~F.from_user.id == user_id,
        F.text | F.photo,
    )
    async def handle_ls_message(message: Message) -> None:
        target_chat_id = db.get_ls_target_chat()
        if target_chat_id is None:
            await message.answer("Бот пока не настроен. Попробуйте позже.")
            return
        await _send_to_max(bot, message, target_chat_id, message.from_user.id)

    # --- ваши сообщения в ЛС (текст или фото) → Max ---
    @dp.message(
        F.from_user.id == user_id,
        F.chat.type == "private",
        F.text | F.photo,
    )
    async def handle_owner_ls(message: Message) -> None:
        target_chat_id = db.get_ls_target_chat()
        if target_chat_id is None:
            await message.answer("Целевой чат не задан. Используйте /setchat.")
            return
        await _send_to_max(bot, message, target_chat_id, user_id)

    # --- пересылка из Max в TG каналы ---
    async def forward_to_tg_loop() -> None:
        while True:
            max_chat_id, caption, photo_urls = await bridge.max_to_tg.get()
            tg_channel_id = db.get_tg_channel_for_max_chat(max_chat_id)
            if tg_channel_id is None:
                print(f"[Max→TG] Нет связки для Max chat {max_chat_id}, пропускаем")
                continue
            try:
                if photo_urls:
                    from max_receiver import _download_photo
                    from aiogram.types import BufferedInputFile, InputMediaPhoto

                    files = []
                    for url in photo_urls:
                        data = await _download_photo(url)
                        if data:
                            files.append(BufferedInputFile(data, filename="photo.jpg"))

                    if files:
                        if len(files) == 1:
                            await bot.send_photo(
                                chat_id=tg_channel_id,
                                photo=files[0],
                                caption=caption,
                            )
                        else:
                            from aiogram.types import InputMediaPhoto
                            media = [
                                InputMediaPhoto(
                                    media=f,
                                    caption=caption if i == 0 else None,
                                )
                                for i, f in enumerate(files)
                            ]
                            await bot.send_media_group(
                                chat_id=tg_channel_id,
                                media=media,
                            )
                    else:
                        await bot.send_message(chat_id=tg_channel_id, text=caption)
                else:
                    await bot.send_message(chat_id=tg_channel_id, text=caption)
            except Exception as e:
                print(f"[Max→TG][ОШИБКА] {e}")

    return bot, dp, forward_to_tg_loop
