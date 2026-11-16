"""Morning check-in contracts and the deterministic summary read by the agents."""

import uuid
from datetime import date

from pydantic import Field

from app.schemas.common import ORMModel, StrictModel

SLEEP_DESCRIPTION = "Hours slept; check-in buckets: 5 = 5 h or less, 9 = 9 h or more"
FEELING_DESCRIPTION = "How the athlete feels (energy, stress, overall): 1 exhausted … 5 great"


class WellnessCheckIn(StrictModel):
    sleep_hours: float | None = Field(default=None, ge=0, le=14, description=SLEEP_DESCRIPTION)
    feeling: int | None = Field(default=None, ge=1, le=5, description=FEELING_DESCRIPTION)


class DailyWellnessRead(ORMModel):
    id: uuid.UUID
    day: date
    sleep_hours: float | None
    feeling: int | None


class WellnessPeriod(StrictModel):
    days_logged: int
    avg_sleep_hours: float | None
    avg_feeling: float | None


class WellnessSummary(StrictModel):
    """Subjective, self-reported. Trends vs the athlete's own average matter more than one
    night; missing days are unknown (never a negative signal)."""

    day: date
    check_in: WellnessCheckIn | None = Field(description="The check-in of `day`, if any")
    last_7d: WellnessPeriod
    previous_28d: WellnessPeriod = Field(description="The 28 days before the last 7 (baseline)")
