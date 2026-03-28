import asyncio
import io
import tempfile
import os
from datetime import datetime
from pymax import MaxClient
from pymax.files import Photo
import bridge
import config


def register(client: MaxClient) -> None:
    @client.on_start
    async def on_start() -> None:
        print("[Max sender] Готов.")
        asyncio.create_task(_send_loop(client))


async def _send_loop(client: MaxClient) -> None:
    while True:
        max_chat_id, text, photo_bytes = await bridge.tg_to_max.get()
        try:
            if photo_bytes:
                # Записываем во временный файл — validate_photo требует path или url
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp.write(photo_bytes)
                    tmp_path = tmp.name
                try:
                    photo = Photo(path=tmp_path)
                    msg = await client.send_message(
                        text=text,
                        chat_id=max_chat_id,
                        notify=True,
                        attachment=photo,
                    )
                finally:
                    os.unlink(tmp_path)  # удаляем после отправки
            else:
                msg = await client.send_message(
                    text=text,
                    chat_id=max_chat_id,
                    notify=True,
                )
            if msg:
                print(f"[TG→Max][chat:{max_chat_id}] Отправлено")
            else:
                print("[TG→Max][ОШИБКА] send_message вернул None")
        except Exception as e:
            print(f"[TG→Max][ОШИБКА] {e}")
