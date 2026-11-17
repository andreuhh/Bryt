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
    BlockWorkoutsOutput,
    CoachChatOutput,
    MechanicalLoadOutput,
    NutritionRecoveryOutput,
    PlanAdjustmentOutput,
    PlanSkeletonOutput,
    RefinementOutput,
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
    cached_prefix: str | None = None
    model: str | None = None
    cache_prefix: bool = True

    @property
    def context(self) -> dict[str, Any]:
        """Stable (cached) and variable context merged, as the model sees them."""
        stable = (
            extract_context(self.cached_prefix, "athlete_context") if self.cached_prefix else {}
        )
        return stable | extract_context(self.prompt)


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
        self,
        *,
        system: str,
        prompt: str,
        output_model: type[T],
        effort: Effort,
        max_tokens: int,
        cached_prefix: str | None = None,
        model: str | None = None,
        cache_prefix: bool = True,
    ) -> LLMResult[T]:
        call = Call(output_model, system, prompt, effort, cached_prefix, model, cache_prefix)
        self.calls.append(call)
        item = self.responses[output_model].popleft()
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, BaseModel):
            item = item(call.context)
        assert isinstance(item, output_model)
        return LLMResult(parsed=item, model=model or self.model, input_tokens=100, output_tokens=50)

    def calls_for(self, output_model: type[BaseModel]) -> list[Call]:
        return [c for c in self.calls if c.output_model is output_model]


def extract_context(prompt: str, tag: str = "context") -> dict[str, Any]:
    match = re.search(rf"<{tag}>\n(.*)\n</{tag}>", prompt, re.S)
    assert match, f"prompt without <{tag}>"
    data: dict[str, Any] = json.loads(match.group(1))
    return data


# --- Builders -----------------------------------------------------------------------------


def skeleton_output(start: date, end: date, split_days: int = 14) -> PlanSkeletonOutput:
    """Two contiguous blocks: [start, start+split-1] and [start+split, end]."""
    cut = start + timedelta(days=split_days)
    return PlanSkeletonOutput.model_validate(
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
                    "end_date": (cut - timedelta(days=1)).isoformat(),
                    "objective": "Volume aerobico",
                    "weeks": [
                        {
                            "week_index": 1,
                            "start_date": start.isoformat(),
                            "load_type": "LOAD",
                            "target_volume_km": 60,
                        }
                    ],
                },
                {
                    "name": "Specifico",
                    "phase": "SPECIFIC",
                    "start_date": cut.isoformat(),
                    "end_date": end.isoformat(),
                    "objective": "Passo maratona",
                    "weeks": [
                        {
                            "week_index": 3,
                            "start_date": cut.isoformat(),
                            "load_type": "LOAD",
                            "target_volume_km": 75,
                        }
                    ],
                },
            ],
            "rationale": "Base aerobica, poi lavoro specifico.",
        }
    )


def _draft(day: date, ctx: dict[str, Any], *, detailed: bool = True) -> dict[str, Any]:
    """Sunday = key long run; Tuesday = DT session with paces copied from the zones."""
    if day.weekday() == 6:
        return {
            "scheduled_date": day.isoformat(),
            "workout_type": "LONG",
            "title": "Lungo 30 km",
            "target_distance_m": 30000,
            "is_key_session": True,
            "structure": [{"kind": "WORK", "distance_m": 30000, "target_zone": "Z2"}],
        }
    if day.weekday() == 1:
        zone = next(z for z in ctx["calibration"]["zones"] if z["code"] == "DT")
        step: dict[str, Any] = {"kind": "WORK", "repeat": 5, "duration_s": 360, "target_zone": "DT"}
        if detailed:
            step |= {"target_pace": zone["pace"], "target_hr": zone["hr"]}
        return {
            "scheduled_date": day.isoformat(),
            "session_slot": "AM",
            "workout_type": "THRESHOLD",
            "title": "5x6' DT",
            "structure": [step],
        }
    return {
        "scheduled_date": day.isoformat(),
        "workout_type": "EASY",
        "title": "Easy 50'",
        "target_duration_s": 3000,
    }


def block_workouts(skip: date | None = None) -> Callable[[dict[str, Any]], BlockWorkoutsOutput]:
    """Every day of context.current_block (optionally skipping one to break coverage)."""

    def build(ctx: dict[str, Any]) -> BlockWorkoutsOutput:
        block = ctx["current_block"]
        day, last = date.fromisoformat(block["start_date"]), date.fromisoformat(block["end_date"])
        workouts = []
        while day <= last:
            if day != skip:
                workouts.append(_draft(day, ctx))
            day += timedelta(days=1)
        return BlockWorkoutsOutput.model_validate({"workouts": workouts})

    return build


def refinement(propose_first_key: bool = False) -> Callable[[dict[str, Any]], RefinementOutput]:
    """Confirms every workout_to_confirm with full detail; optionally proposes moving the
    first far-ahead key session one day later."""

    def build(ctx: dict[str, Any]) -> RefinementOutput:
        confirmed = [
            {
                "workout_id": w["id"],
                "workout": _draft(date.fromisoformat(w["scheduled_date"]), ctx),
            }
            for w in ctx["workouts_to_confirm"]
        ]
        proposals = []
        if propose_first_key and ctx["upcoming_key_sessions"]:
            key = ctx["upcoming_key_sessions"][0]
            moved = date.fromisoformat(key["scheduled_date"]) + timedelta(days=1)
            proposals.append(
                {
                    "workout_id": key["id"],
                    "proposed": _draft(moved, ctx, detailed=False)
                    | {"workout_type": "LONG", "title": "Lungo 32 km", "is_key_session": True},
                    "reason": "Recupero più lungo dopo il cedimento meccanico",
                }
            )
        return RefinementOutput.model_validate(
            {
                "confirmed": confirmed,
                "key_session_proposals": proposals,
                "notes": "Settimana confermata.",
            }
        )

    return build


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
