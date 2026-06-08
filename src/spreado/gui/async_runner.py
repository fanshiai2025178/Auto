"""在后台线程运行 asyncio 协程，避免阻塞 Tkinter 主线程。"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Coroutine, Optional, TypeVar

T = TypeVar("T")


class AsyncTaskRunner:
    """在独立线程事件循环中执行协程。"""

    def __init__(self):
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def run(
        self,
        coro: Coroutine[Any, Any, T],
        *,
        on_success: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
        on_finally: Optional[Callable[[], None]] = None,
    ) -> None:
        if self._busy:
            raise RuntimeError("已有任务正在运行")

        self._busy = True

        def _worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(coro)
                if on_success:
                    on_success(result)
            except BaseException as exc:
                if on_error:
                    on_error(exc)
            finally:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()
                self._busy = False
                if on_finally:
                    on_finally()

        threading.Thread(target=_worker, daemon=True).start()
