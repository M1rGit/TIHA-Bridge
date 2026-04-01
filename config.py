import os
from dotenv import load_dotenv

load_dotenv()

MAX_PHONE      = os.getenv("MAX_PHONE")
TG_BOT_TOKEN   = os.getenv("TG_BOT_TOKEN")
TG_OWNER_ID    = int(os.getenv("TG_OWNER_ID"))
DISCORD_TOKEN  = os.getenv("DISCORD_TOKEN")

if not all([MAX_PHONE, TG_BOT_TOKEN, TG_OWNER_ID, DISCORD_TOKEN]):
    raise RuntimeError("Не все переменные окружения заданы. Проверьте .env")
