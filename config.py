import os
from dotenv import load_dotenv

load_dotenv()

MAX_PHONE = os.getenv("MAX_PHONE")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_USER_ID = int(os.getenv("TG_USER_ID"))

if not all([MAX_PHONE, TG_BOT_TOKEN, TG_USER_ID]):
    raise RuntimeError("Не все переменные окружения заданы. Проверьте .env файл.")
