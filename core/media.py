import asyncio
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


async def _run_ffmpeg(*args: str) -> bytes | None:
    """Запускает ffmpeg и возвращает содержимое выходного файла."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("ffmpeg error: %s", stderr.decode())
            return None

        # Последний аргумент — путь к выходному файлу
        out_path = args[-1]
        with open(out_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("ffmpeg not found. Install: brew install ffmpeg")
        return None
    except Exception:
        logger.exception("ffmpeg failed")
        return None


async def to_mp3(data: bytes, input_ext: str = "ogg") -> bytes | None:
    """Конвертирует аудио в MP3."""
    with (
        tempfile.NamedTemporaryFile(suffix=f".{input_ext}", delete=False) as inp,
        tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as out,
    ):
        inp.write(data)
        inp_path = inp.name
        out_path = out.name

    try:
        return await _run_ffmpeg(
            "-i", inp_path,
            "-codec:a", "libmp3lame",
            "-qscale:a", "2",
            out_path,
        )
    finally:
        os.unlink(inp_path)
        os.unlink(out_path)


async def to_mp4(data: bytes, input_ext: str = "mp4") -> bytes | None:
    """Конвертирует видео в MP4 (перекодирует если нужно)."""
    with (
        tempfile.NamedTemporaryFile(suffix=f".{input_ext}", delete=False) as inp,
        tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as out,
    ):
        inp.write(data)
        inp_path = inp.name
        out_path = out.name

    try:
        return await _run_ffmpeg(
            "-i", inp_path,
            "-codec:v", "libx264",
            "-codec:a", "aac",
            "-movflags", "+faststart",
            out_path,
        )
    finally:
        os.unlink(inp_path)
        os.unlink(out_path)
