"""Pydantic request/response models for the agent API."""

from datetime import datetime

from pydantic import BaseModel

from db.models import JobStatus


class ConvertRequest(BaseModel):
    model: str = "openrouter/google/gemini-3-flash-preview"
    api_key: str | None = None
    max_retries: int = 3
    dpi: int = 300


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    model: str = ""
    total_pages: int = 0
    created_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    input_filenames: list[str] = []
    has_pdf: bool = False
    has_tex: bool = False
