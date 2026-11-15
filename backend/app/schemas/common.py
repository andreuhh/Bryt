"""Building blocks shared across schemas."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORMModel(BaseModel):
    """Read schemas built from SQLModel rows."""

    model_config = ConfigDict(from_attributes=True)


class StrictModel(BaseModel):
    """Inbound payloads and agent outputs: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


class HrRange(StrictModel):
    min_bpm: int = Field(gt=0, le=240)
    max_bpm: int = Field(gt=0, le=240)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.min_bpm > self.max_bpm:
            raise ValueError("min_bpm must be <= max_bpm")
        return self


class PaceRange(StrictModel):
    """Pace in seconds per km. `fast` is the lower number."""

    fast_s_per_km: float = Field(gt=0)
    slow_s_per_km: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.fast_s_per_km > self.slow_s_per_km:
            raise ValueError("fast_s_per_km must be <= slow_s_per_km")
        return self
