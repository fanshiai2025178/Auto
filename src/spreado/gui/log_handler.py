"""将日志输出桥接到 Tkinter 文本控件。"""

from __future__ import annotations

import logging
import queue
from typing import Callable, Optional


class GuiLogHandler(logging.Handler):
    """线程安全的 GUI 日志 Handler，通过回调投递到主线程。"""

    def __init__(self, post_fn: Callable[[str], None]):
        super().__init__()
        self._post_fn = post_fn
        self.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s", "%H:%M:%S")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._post_fn(msg)
        except Exception:
            self.handleError(record)


def attach_gui_logging(post_fn: Callable[[str], None]) -> GuiLogHandler:
    """挂载 GUI 日志 Handler，返回 handler 供后续移除。"""
    from spreado.utils.log import setup_logging

    setup_logging()
    handler = GuiLogHandler(post_fn)
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    return handler
