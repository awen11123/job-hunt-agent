from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class _TrackerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TrackerApplication(_TrackerModel):
    id: str
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    applied_date: date | None = None
    location: str | None = None
    status: str = Field(min_length=1)
    next_step: str | None = None
    next_time: date | None = None
    job_url: HttpUrl | None = None
    notes: str | None = None


class TrackerApplicationDraft(_TrackerModel):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    applied_date: date = Field(default_factory=date.today)
    location: str | None = None
    status: str = Field(default="已投递", min_length=1)
    next_step: str = "等待筛选"
    next_time: date | None = None
    job_url: HttpUrl | None = None
    notes: str | None = None


class TrackerApplicationPatch(_TrackerModel):
    company: str | None = Field(default=None, min_length=1)
    role: str | None = Field(default=None, min_length=1)
    applied_date: date | None = None
    location: str | None = None
    status: str | None = Field(default=None, min_length=1)
    next_step: str | None = None
    next_time: date | None = None
    job_url: HttpUrl | None = None
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_empty_patch(cls, value: Any) -> Any:
        if isinstance(value, dict) and not value:
            raise ValueError("empty patch is not allowed")
        if isinstance(value, dict):
            for field_name in ("company", "role", "status"):
                if field_name in value and value[field_name] is None:
                    raise ValueError(f"{field_name} cannot be null")
        return value
