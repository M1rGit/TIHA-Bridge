import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pymax import MaxClient

from core.bus import MessageBus
from adapters.max.adapter import MaxAdapter
from adapters.telegram.adapter import TelegramAdapter
from adapters.discord.adapter import DiscordAdapter
from db.database import init as db_init
import config
from core.adapter_config import is_enabled
logger = logging.getLogger(__name__)


def setup_logging() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Консоль — INFO
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))

    # Файл — DEBUG и выше (всё)
    file_handler = RotatingFileHandler(
        log_dir / "bridge.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


async def main() -> None:
    setup_logging()
    db_init()

    bus = MessageBus()

    max_client  = MaxClient(phone=config.MAX_PHONE, work_dir="cache")
    max_adapter = MaxAdapter(client=max_client, bus=bus)
    tg_adapter  = TelegramAdapter(token=config.TG_BOT_TOKEN, owner_id=config.TG_OWNER_ID, bus=bus)
    dc_adapter  = DiscordAdapter(token=config.DISCORD_TOKEN, bus=bus)

    bus.register_adapter(max_adapter)
    bus.register_adapter(tg_adapter)
    bus.register_adapter(dc_adapter)

    # start только если включён
    tasks = [bus.run()]

    if is_enabled("max"):
        await max_adapter.start()
        tasks.append(max_client.start())
    else:
        logger.info("Max adapter disabled — skipping start")

    if is_enabled("telegram"):
        tasks.append(tg_adapter.start())
    else:
        logger.info("Telegram adapter disabled — skipping start")

    if is_enabled("discord"):
        tasks.append(dc_adapter.start())
    else:
        logger.info("Discord adapter disabled — skipping start")

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
