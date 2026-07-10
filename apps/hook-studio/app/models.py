from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    CLIENT = "client"
    ADMIN = "admin"


class Mode(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class AccessCodeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")
    code: str = Field(min_length=6, max_length=256)
    client_name: str = Field(min_length=1, max_length=100)
    role: Role = Role.CLIENT
    daily_video_limit: int = Field(default=100, ge=0, le=100)
    enabled: bool = True


class Principal(BaseModel):
    code_id: str
    client_name: str
    role: Role
    daily_video_limit: int


class LoginRequest(BaseModel):
    access_code: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    principal: Principal
    expires_at: datetime


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    request_id: str | None = None


class EventAction(StrEnum):
    GENERATE = "generate"
    PREVIEW = "preview"
    DOWNLOAD = "download"
    REGENERATE = "regenerate"
    DELETE = "delete"


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ts: datetime
    access_code: str
    mode: Mode
    preset_id: str
    template_version: str
    prompt_user: str
    prompt_final: str
    params: dict[str, Any] = Field(default_factory=dict)
    model: str
    result_url: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    cost_units: int = Field(default=0, ge=0)
    action: EventAction
    job_id: str
    client_id: str
    queue_name: Literal["image", "video"]
    queue_wait_ms: int | None = Field(default=None, ge=0)
    provider_attempt: int | None = Field(default=None, ge=0)
    skill_trace: dict[str, Any] | None = None
    error_code: str | None = None


class UsageSnapshot(BaseModel):
    day_cn: str
    client_id: str
    client_reserved: int
    client_succeeded: int
    client_failed: int
    global_reserved: int
    global_succeeded: int
    client_limit: int
    global_limit: int

