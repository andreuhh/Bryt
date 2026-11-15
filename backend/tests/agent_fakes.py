"""Deterministic LLM double + builders of valid agent outputs."""

import json
import re
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, TypeVar

from pydantic import BaseModel

from app.agents.llm import Effort, LLMResult
from app.schemas.agents import (
    CoachChatOutput,
    MechanicalLoadOutput,
    NutritionRecoveryOutput,
    PlanAdjustmentOutput,
    PlanGenerationOutput,
)
from tests.factories import mechanical_load_payload, nutrition_recovery_payload

T = TypeVar("T", bound=BaseModel)

Response = BaseModel | Exception | Callable[[dict[str, Any]], BaseModel]


@dataclass
class Call:
    output_model: type[BaseModel]
    system: str
    prompt: str
    effort: str

    @property
    def context(self) -> dict[str, Any]:
        return extract_context(self.prompt)


@dataclass
class FakeLLM:
    """Queue of responses per output model; a callable receives the parsed <context>."""

    responses: dict[type[BaseModel], deque[Response]] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    model: str = "fake-model"

    def queue(self, output_model: type[BaseModel], *items: Response) -> "FakeLLM":
        self.responses.setdefault(output_model, deque()).extend(items)
        return self

    async def generate(
        self, *, system: str, prompt: str, output_model: type[T], effort: Effort, max_tokens: int
    ) -> LLMResult[T]:
        self.calls.append(Call(output_model, system, prompt, effort))
        item = self.responses[output_model].popleft()
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, BaseModel):
            item = item(extract_context(prompt))
        assert isinstance(item, output_model)
        return LLMResult(parsed=item, model=self.model, input_tokens=100, output_tokens=50)

    def calls_for(self, output_model: type[BaseModel]) -> list[Call]:
        return [c for c in self.calls if c.output_model is output_model]


def extract_context(prompt: str) -> dict[str, Any]:
    match = re.search(r"<context>\n(.*)\n</context>", prompt, re.S)
    assert match, "prompt without <context>"
    data: dict[str, Any] = json.loads(match.group(1))
    return data


# --- Builders -----------------------------------------------------------------------------


def plan_output(
    start: date, end: date, *, weekday_override: date | None = None
) -> PlanGenerationOutput:
    first = weekday_override or start
    return PlanGenerationOutput.model_validate(
        {
            "plan_name": "Maratona sub 2h55",
            "methodology": "DOUBLE_THRESHOLD",
            "goal_summary": "Scendere sotto 2h55 in maratona",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "blocks": [
                {
                    "name": "Base",
                    "phase": "BASE",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "objective": "Volume aerobico",
                    "weeks": [
                        {"week_index": 1, "start_date": start.isoformat(), "load_type": "LOAD"}
                    ],
                }
            ],
            "workouts": [
                {
                    "scheduled_date": first.isoformat(),
                    "session_slot": "AM",
                    "workout_type": "THRESHOLD",
                    "title": "5x6' DT",
                    "structure": [
                        {"kind": "WARMUP", "duration_s": 900, "target_zone": "Z2"},
                        {"kind": "WORK", "repeat": 5, "duration_s": 360, "target_zone": "DT"},
                    ],
                },
                {
                    "scheduled_date": (start + timedelta(days=1)).isoformat(),
                    "workout_type": "EASY",
                    "title": "Easy 50'",
                    "target_duration_s": 3000,
                },
            ],
            "rationale": "Base aerobica con doppia soglia controllata.",
        }
    )


def mechanical_output(**overrides: Any) -> MechanicalLoadOutput:
    return MechanicalLoadOutput.model_validate(mechanical_load_payload(**overrides))


def no_adjustment_mechanical() -> MechanicalLoadOutput:
    return mechanical_output(plan_adjustment_needed=False, adjustment_request=None, alerts=[])


def nutrition_output() -> NutritionRecoveryOutput:
    return NutritionRecoveryOutput.model_validate(nutrition_recovery_payload())


def adjust_all(action: str = "REDUCE") -> Callable[[dict[str, Any]], PlanAdjustmentOutput]:
    """Builds a valid adjustment for whatever workouts the context asks to review."""

    def build(ctx: dict[str, Any]) -> PlanAdjustmentOutput:
        adjustments = []
        for w in ctx["workouts_to_review"]:
            adj: dict[str, Any] = {"workout_id": w["id"], "action": action, "reason": "Scarico"}
            if action in ("REDUCE", "REPLACE"):
                adj["new_workout"] = {
                    "scheduled_date": w["scheduled_date"],
                    "workout_type": "EASY",
                    "title": "Easy su sterrato 40'",
                    "target_duration_s": 2400,
                }
            adjustments.append(adj)
        return PlanAdjustmentOutput.model_validate(
            {"adjustments": adjustments, "rationale": "Ridotto l'impatto dopo il cedimento."}
        )

    return build


def chat_output(with_adjustment: bool) -> CoachChatOutput:
    return CoachChatOutput.model_validate(
        {
            "reply": "Ho preparato una proposta di modifica, confermala per applicarla.",
            "proposed_adjustment": {
                "reason": "Influenza",
                "days_affected": 3,
                "guidance": "Solo riposo o easy brevi",
            }
            if with_adjustment
            else None,
        }
    )
