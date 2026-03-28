import asyncio
from pymax import MaxClient
import config
import db
import max_receiver
import max_sender
import tg_bot

db.init()

max_client = MaxClient(phone=config.MAX_PHONE, work_dir="cache")


@max_client.on_start
async def register_max_chats() -> None:
    """Регистрируем все известные чаты Max при старте."""
    for chat in max_client.chats + max_client.dialogs:
        title = getattr(chat, "title", None) or str(chat.id)
        db.upsert_max_chat(chat.id, title)
    print(f"[Max] Зарегистрировано чатов: {len(max_client.chats + max_client.dialogs)}")


max_receiver.register(max_client)
max_sender.register(max_client)

bot, dp, forward_loop = tg_bot.create_bot(config.TG_BOT_TOKEN, config.TG_USER_ID)


async def main() -> None:
    await asyncio.gather(
        max_client.start(),
        dp.start_polling(bot),
        forward_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
