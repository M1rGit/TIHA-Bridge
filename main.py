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

    await max_adapter.start()

    await asyncio.gather(
        max_client.start(),
        tg_adapter.start(),
        dc_adapter.start(),
        bus.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
