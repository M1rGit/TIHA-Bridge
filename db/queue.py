# db/queue.py — legacy wrapper, импортирует из db.messages
# Используйте напрямую db.messages.PersistentQueue

from db.messages import PersistentQueue

__all__ = ["PersistentQueue"]
