"""Daily wellness: the morning check-in (and, later, nightly device data via Intervals.icu)."""

from datetime import date

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.models.base import IdMixin, TenantMixin, TimestampMixin


class DailyWellness(IdMixin, TimestampMixin, TenantMixin, table=True):
    """One row per athlete per local day. Both answers are optional: a skipped check-in is
    unknown, never bad."""

    __tablename__ = "daily_wellness"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_wellness_user_day"),)

    day: date = Field(index=True)
    # Check-in buckets: 5 = "5 h or less", 9 = "9 h or more"
    sleep_hours: float | None = Field(default=None, ge=0, le=14)
    # How the athlete feels (energy, stress, overall): 1 = exhausted … 5 = great
    feeling: int | None = Field(default=None, ge=1, le=5)
