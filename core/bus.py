from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from core.message import UniversalMessage
from core.router import Router
from core.adapter import BaseAdapter
from db.queue import PersistentQueue
from db import database as db

logger = logging.getLogger(__name__)


class MessageBus:
    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}
        self._router   = Router()
        self._queue    = PersistentQueue()

    def register_adapter(self, adapter: BaseAdapter) -> None:
        self._adapters[adapter.platform] = adapter
        logger.info("Adapter registered: %s", adapter.platform)

    async def publish(self, msg: UniversalMessage) -> None:
        targets = self._router.get_targets(msg)
        if not targets:
            logger.debug(
                "No routes for %s/%s — dropping",
                msg.source_platform, msg.source_chat_id,
            )
            return
        for sink_platform, sink_chat_id in targets:
            self._queue.push(msg, sink_platform, sink_chat_id)
            logger.debug("Queued %s → %s/%s", msg.id, sink_platform, sink_chat_id)

    async def run(self) -> None:
        logger.info("MessageBus worker started")
        while True:
            try:
                ready = self._queue.pop_ready()
                for msg, sink_platform, sink_chat_id in ready:
                    adapter = self._adapters.get(sink_platform)
                    if not adapter:
                        logger.warning("No adapter for platform: %s", sink_platform)
                        continue
                    await self._deliver(adapter, msg, sink_chat_id)
            except Exception:
                logger.exception("Bus worker error")
            await asyncio.sleep(0.5)

    async def _deliver(
        self,
        adapter: BaseAdapter,
        msg: UniversalMessage,
        sink_chat_id: str,
    ) -> None:
        try:
            success = await adapter.send(msg, sink_chat_id)
            now     = datetime.utcnow().isoformat()
            status  = "delivered" if success else "failed"

            db.log_message(
                msg_id=            msg.id,
                source_platform=   msg.source_platform,
                source_chat_id=    msg.source_chat_id,
                source_chat_title= msg.source_chat_title,
                source_user_id=    msg.source_user_id,
                source_user_name=  msg.source_user_name,
                sink_platform=     adapter.platform,
                sink_chat_id=      sink_chat_id,
                text=              msg.text,
                media_url=         msg.media_url,
                status=            status,
                retry_count=       msg.retry_count,
                timestamp=         msg.timestamp.isoformat(),
                delivered_at=      now if success else None,
            )

            if success:
                self._queue.mark_delivered(msg.id)
                logger.info("Delivered %s → %s/%s", msg.id, adapter.platform, sink_chat_id)
            else:
                has_retries = self._queue.schedule_retry(msg.id, msg.retry_count)
                if not has_retries:
                    logger.error(
                        "Message %s failed after all retries → %s/%s",
                        msg.id, adapter.platform, sink_chat_id,
                    )
        except Exception:
            logger.exception("Delivery error for %s", msg.id)
            self._queue.schedule_retry(msg.id, msg.retry_count)
