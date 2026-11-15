"""Shared column helpers and mixins for all BRYT tables.

Mixin fields use `sa_type` / `sa_column_kwargs` (never a shared `sa_column=Column(...)`),
so every table gets its own Column instance.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def enum_column(enum_cls: type[StrEnum], *, nullable: bool = False, index: bool = False) -> Any:
    """VARCHAR-backed enum column (no native PG type → painless migrations)."""
    return Column(
        SAEnum(
            enum_cls,
            native_enum=False,
            create_constraint=False,
            length=32,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=nullable,
        index=index,
    )


def jsonb_column(*, nullable: bool = False) -> Any:
    return Column(JSONB, nullable=nullable)


class IdMixin(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class TimestampMixin(SQLModel):
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "nullable": False},
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now(), "nullable": False},
    )


class TenantMixin(SQLModel):
    """Every domain row belongs to exactly one user (multi-tenant isolation)."""

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
