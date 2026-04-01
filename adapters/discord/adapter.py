from __future__ import annotations
import asyncio
import io
import logging
from datetime import datetime

import discord
from discord.ext import commands

from core.adapter import BaseAdapter
from core.media import to_mp3, to_mp4
from core.message import UniversalMessage
from db import database as db

logger = logging.getLogger(__name__)


class DiscordAdapter(BaseAdapter):
    platform = "discord"

    def __init__(self, token: str, bus) -> None:
        self._token = token
        self._bus   = bus

        intents                 = discord.Intents.default()
        intents.message_content = True
        intents.guilds          = True

        self._bot  = commands.Bot(command_prefix="!", intents=intents)
        self._tree = self._bot.tree
        self._register_handlers()

    def _register_handlers(self) -> None:
        bot = self._bot

        @bot.event
        async def on_ready() -> None:
            await self._tree.sync()
            logger.info("Discord adapter ready: %s", bot.user)
            for guild in bot.guilds:
                for channel in guild.text_channels:
                    db.upsert_chat(
                        "discord", str(channel.id),
                        f"{guild.name}#{channel.name}",
                    )

        @bot.event
        async def on_guild_channel_create(channel) -> None:
            if isinstance(channel, discord.TextChannel):
                db.upsert_chat(
                    "discord", str(channel.id),
                    f"{channel.guild.name}#{channel.name}",
                )

        @bot.event
        async def on_message(message: discord.Message) -> None:
            if message.author.bot:
                return
            if not isinstance(message.channel, discord.TextChannel):
                return

            photo_bytes      = None
            audio_bytes      = None
            video_note_bytes = None

            for attachment in message.attachments:
                ct = attachment.content_type or ""
                try:
                    if ct.startswith("image/") and not photo_bytes:
                        photo_bytes = await attachment.read()
                    elif ct.startswith("audio/") and not audio_bytes:
                        raw = await attachment.read()
                        audio_bytes = await to_mp3(raw, input_ext="ogg")
                    elif ct.startswith("video/") and not video_note_bytes:
                        raw = await attachment.read()
                        video_note_bytes = await to_mp4(raw, input_ext="mp4")
                except Exception as e:
                    logger.error("Discord attachment read failed: %s", e)

            universal = UniversalMessage(
                source_platform  = "discord",
                source_chat_id   = str(message.channel.id),
                source_user_id   = str(message.author.id),
                text             = message.content or "",
                photo_bytes      = photo_bytes,
                audio_bytes      = audio_bytes,
                video_note_bytes = video_note_bytes,
                timestamp        = message.created_at.replace(tzinfo=None),
            )

            from core.identity import resolve_chat_title

# После создания universal:
            universal.source_user_name  = message.author.display_name or message.author.name
            universal.source_chat_title = resolve_chat_title("discord", str(message.channel.id))

            logger.info(
                "Discord message received: chat=%s user=%s text=%r",
                message.channel.id, message.author.id, message.content
            )
            await self._bus.publish(universal)
            await bot.process_commands(message)

        @self._tree.command(name="routes", description="Показать маршруты")
        async def slash_routes(interaction: discord.Interaction) -> None:
            rows = db.get_all_routes()
            if not rows:
                await interaction.response.send_message("Маршрутов нет.", ephemeral=True)
                return
            lines = [
                f"`{r['id']}` {r['source_platform']}/{r['source_title'] or r['source_chat_id']}"
                f" → {r['sink_platform']}/{r['sink_title'] or r['sink_chat_id']}"
                for r in rows
            ]
            await interaction.response.send_message(
                "**Маршруты:**\n" + "\n".join(lines), ephemeral=True
            )

    async def start(self) -> None:
        asyncio.create_task(self._bot.start(self._token))
        logger.info("Discord adapter starting")

    async def send(self, msg: UniversalMessage, target_chat_id: str) -> bool:
        try:
            channel = self._bot.get_channel(int(target_chat_id))
            if not channel:
                logger.error("Discord: channel %s not found", target_chat_id)
                return False

            ts      = msg.timestamp.strftime("%d.%m.%Y %H:%M:%S")
            text    = msg.text or ""
            user_label = msg.source_user_name or msg.source_user_id
            chat_label = msg.source_chat_title or msg.source_chat_id
            caption = (
                f"🔀 **{msg.source_platform}** → discord\n"
                f"👤 {user_label} | 💬 {chat_label}\n"
                f"🕐 {ts}" + (f"\n\n{text}" if text else "")
            )

            if msg.photo_bytes:
                file = discord.File(io.BytesIO(msg.photo_bytes), filename="photo.jpg")
                await channel.send(content=caption, file=file)
            elif msg.audio_bytes:
                file = discord.File(io.BytesIO(msg.audio_bytes), filename="voice.mp3")
                await channel.send(content=caption, file=file)
            elif msg.video_note_bytes:
                file = discord.File(io.BytesIO(msg.video_note_bytes), filename="video.mp4")
                await channel.send(content=caption, file=file)
            else:
                await channel.send(content=caption)

            return True
        except Exception:
            logger.exception("Discord send failed")
            return False
