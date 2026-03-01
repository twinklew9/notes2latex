"""Progress callback system using contextvars for non-intrusive event emission."""

import contextvars
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class EventType(str, Enum):
    JOB_STARTED = "job_started"
    PAGE_GENERATING = "page_generating"
    PAGE_COMPILING = "page_compiling"
    PAGE_COMPILED_OK = "page_compiled_ok"
    PAGE_FIX_ATTEMPT = "page_fix_attempt"
    PAGE_DONE = "page_done"
    FINALIZING = "finalizing"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"


@dataclass
class ProgressEvent:
    event_type: EventType
    page: int = 0
    total_pages: int = 0
    retry: int = 0
    max_retries: int = 0
    message: str = ""
    extra: dict = field(default_factory=dict)


class ProgressCallback(Protocol):
    async def __call__(self, event: ProgressEvent) -> None: ...


_progress_callback_var: contextvars.ContextVar[ProgressCallback | None] = contextvars.ContextVar(
    "progress_callback", default=None
)


def set_progress_callback(callback: ProgressCallback | None) -> contextvars.Token:
    """Set the progress callback for the current context."""
    return _progress_callback_var.set(callback)


def get_progress_callback() -> ProgressCallback | None:
    """Get the current progress callback, or None."""
    return _progress_callback_var.get()


async def emit(event: ProgressEvent) -> None:
    """Emit a progress event if a callback is set."""
    callback = _progress_callback_var.get()
    if callback is not None:
        await callback(event)
