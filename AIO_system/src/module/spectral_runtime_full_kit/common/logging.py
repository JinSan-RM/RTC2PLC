from __future__ import annotations

import logging as _stdlib_logging


def configure_logging(level: str = "INFO") -> None:
    """Configure fallback logging for standalone use outside the main app."""
    if _main_logger_class() is not None:
        return
    numeric_level = getattr(_stdlib_logging, level.upper(), _stdlib_logging.INFO)
    _stdlib_logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


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
    logger = _main_logger_class()
    if logger is None:
        return False

    logger.log(f"[{level}] [{name}] {message}", skip_frames=skip_frames)
    return True


def _main_logger_class():
    try:
        from src.utils.logger import Logger
    except Exception:
        return None
    return Logger


def _format_message(message, args) -> str:
    text = str(message)
    if not args:
        return text
    try:
        return text % args
    except Exception:
        return " ".join([text, *(str(arg) for arg in args)])
