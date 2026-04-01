from __future__ import annotations
from abc import ABC, abstractmethod
from core.message import UniversalMessage


class BaseAdapter(ABC):
    platform: str  # переопределяется в каждом адаптере

    @abstractmethod
    async def start(self) -> None:
        """Запускает приём сообщений платформы."""
        ...

    @abstractmethod
    async def send(self, msg: UniversalMessage, target_chat_id: str) -> bool:
        """
        Отправляет сообщение в target_chat_id на своей платформе.
        Возвращает True при успехе, False при сбое.
        """
        ...
