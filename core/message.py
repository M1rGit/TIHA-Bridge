from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UniversalMessage:
    source_platform:   str
    source_chat_id:    str
    source_user_id:    str
    text:              str
    timestamp:         datetime
    id:                str           = field(default_factory=lambda: str(uuid.uuid4()))
    photo_bytes:       bytes | None  = None
    audio_bytes:       bytes | None  = None
    video_note_bytes:  bytes | None  = None
    media_url:         str | None    = None   # ссылка на фото/медиа для БД
    source_user_name:  str | None    = None   # резолвится адаптером
    source_chat_title: str | None    = None   # резолвится адаптером
    status:            str           = "pending"
    retry_count:       int           = 0

    def to_dict(self) -> dict:
        return {
            "id":                self.id,
            "source_platform":   self.source_platform,
            "source_chat_id":    self.source_chat_id,
            "source_user_id":    self.source_user_id,
            "text":              self.text,
            "timestamp":         self.timestamp.isoformat(),
            "photo_bytes":       self.photo_bytes,
            "audio_bytes":       self.audio_bytes,
            "video_note_bytes":  self.video_note_bytes,
            "media_url":         self.media_url,
            "source_user_name":  self.source_user_name,
            "source_chat_title": self.source_chat_title,
            "status":            self.status,
            "retry_count":       self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> UniversalMessage:
        return cls(
            id=                d["id"],
            source_platform=   d["source_platform"],
            source_chat_id=    d["source_chat_id"],
            source_user_id=    d["source_user_id"],
            text=              d["text"],
            timestamp=         datetime.fromisoformat(d["timestamp"]),
            photo_bytes=       d.get("photo_bytes"),
            audio_bytes=       d.get("audio_bytes"),
            video_note_bytes=  d.get("video_note_bytes"),
            media_url=         d.get("media_url"),
            source_user_name=  d.get("source_user_name"),
            source_chat_title= d.get("source_chat_title"),
            status=            d.get("status", "pending"),
            retry_count=       d.get("retry_count", 0),
        )
