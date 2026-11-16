"""Ingestion contracts: Intervals.icu sync / webhook and manual .fit upload."""

import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.activity import ActivityRead
from app.schemas.common import StrictModel


class IntervalsSyncRequest(StrictModel):
    oldest: date | None = Field(default=None, description="Default: today - sync window")
    newest: date | None = Field(default=None, description="Default: today")
    analyze: bool = Field(
        default=True,
        description="False = history backfill: import without running the agents (no LLM cost)",
    )


class SyncItemStatus(StrEnum):
    IMPORTED = "IMPORTED"
    ALREADY_PRESENT = "ALREADY_PRESENT"
    UNSUPPORTED_SPORT = "UNSUPPORTED_SPORT"
    NO_FILE = "NO_FILE"  # e.g. Strava-sourced activities: no original file via API
    FAILED = "FAILED"


class SyncItem(StrictModel):
    external_id: str
    name: str | None = None
    sport: str | None = None
    status: SyncItemStatus
    activity_id: uuid.UUID | None = None
    detail: str | None = None


class IntervalsSyncResult(StrictModel):
    oldest: date
    newest: date
    items: list[SyncItem]

    def count(self, status: SyncItemStatus) -> int:
        return sum(1 for item in self.items if item.status == status)


class UploadFitResult(StrictModel):
    created: bool = Field(description="False when the same .fit was already ingested")
    activity: ActivityRead


# --- Intervals.icu payloads (external: unknown keys tolerated) ---------------------------


class IntervalsActivity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None
    type: str | None = None
    start_date_local: str | None = None
    file_type: str | None = None
    source: str | None = None


class IntervalsWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    athlete_id: str
    type: str
    timestamp: str | None = None
    activity: dict[str, Any] | None = None


class IntervalsWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    secret: str
    events: list[IntervalsWebhookEvent] = Field(default_factory=list)


class WebhookAck(StrictModel):
    accepted: int
    ignored: int
