from __future__ import annotations

import logging as _stdlib_logging


def get_logger(name: str):
    return MainAppLogger(name)


class MainAppLogger:
    """Small logging.Logger-compatible bridge to the AIO app logger."""

    def __init__(self, name: str):
        self.name = name
        self._fallback = _stdlib_logging.getLogger(name)

    def debug(self, message, *args, **kwargs):
        self._emit("DEBUG", message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self._emit("INFO", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._emit("WARNING", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._emit("ERROR", message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        kwargs.setdefault("exc_info", True)
        self._emit("ERROR", message, *args, **kwargs)

    def _emit(self, level: str, message, *args, **kwargs):
        formatted = _format_message(message, args)
        if _emit_main_log(level, self.name, formatted, skip_frames=4):
            return
        getattr(self._fallback, level.lower())(formatted, exc_info=kwargs.get("exc_info", False))


def _emit_main_log(level: str, name: str, message: str, *, skip_frames: int) -> bool:
    try:
        from src.utils.logger import Logger
    except Exception:
        return False

    Logger.log(f"[{level}] [{name}] {message}", skip_frames=skip_frames)
    return True


def _format_message(message, args) -> str:
    text = str(message)
    if not args:
        return text
    try:
        return text % args
    except Exception:
        return " ".join([text, *(str(arg) for arg in args)])
