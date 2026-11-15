import uuid

import pytest
from pydantic import BaseModel, ValidationError

from app.models import UserLifestyleProfile
from app.models.enums import AthleteBackground, TrainingSlot, WorkType
from app.schemas.agents import (
    BlockWorkoutsOutput,
    CoachChatOutput,
    MechanicalLoadOutput,
    NutritionRecoveryOutput,
    PlanAdjustmentOutput,
    PlanSkeletonOutput,
    RefinementOutput,
    WorkoutAdjustment,
)
from app.schemas.common import PaceRange
from app.schemas.training import WorkoutStep
from app.schemas.user import ProfileCreate, ProfileRead
from tests.factories import mechanical_load_payload, nutrition_recovery_payload, profile_payload

# --- Profile -----------------------------------------------------------------------------


def test_profile_valid() -> None:
    profile = ProfileCreate.model_validate(profile_payload())
    assert profile.background is AthleteBackground.ROAD


@pytest.mark.parametrize(
    "overrides",
    [
        {"resting_hr": 175},  # resting >= threshold
        {"threshold_hr": 195},  # threshold >= max
        {"available_days": []},
        {"intervals_athlete_id": "12345", "intervals_api_key": "k"},  # missing 'i' prefix
        {"intervals_athlete_id": "i12345"},  # key missing
        {"unknown_field": 1},
    ],
)
def test_profile_invalid(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProfileCreate.model_validate(profile_payload(**overrides))


def test_api_key_is_secret_in_inbound_payload() -> None:
    profile = ProfileCreate.model_validate(
        profile_payload(intervals_athlete_id="i12345", intervals_api_key="super-secret")
    )
    assert "super-secret" not in repr(profile)
    assert "super-secret" not in profile.model_dump_json()


def test_profile_read_never_exposes_api_key() -> None:
    row = UserLifestyleProfile(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        background=AthleteBackground.TRAIL,
        preferred_slot=TrainingSlot.EVENING,
        work_type=WorkType.PHYSICAL,
        available_days=[],
        terrain_access=[],
        intervals_athlete_id="i12345",
        intervals_api_key_encrypted="gAAAA-encrypted",
    )
    dumped = ProfileRead.model_validate(row).model_dump()
    assert dumped["intervals_connected"] is True
    assert not any("api_key" in key for key in dumped)
    assert "gAAAA-encrypted" not in str(dumped)


# --- Training ----------------------------------------------------------------------------


def test_pace_range_ordering() -> None:
    with pytest.raises(ValidationError):
        PaceRange(fast_s_per_km=300, slow_s_per_km=240)


def test_workout_step_requires_length() -> None:
    with pytest.raises(ValidationError):
        WorkoutStep.model_validate({"kind": "WORK"})


# --- Agent outputs -----------------------------------------------------------------------


def test_mechanical_load_output_valid() -> None:
    out = MechanicalLoadOutput.model_validate(mechanical_load_payload())
    assert out.cadence_hr_divergence.detected
    assert out.plan_adjustment_needed


def test_mechanical_load_adjustment_consistency() -> None:
    with pytest.raises(ValidationError):
        MechanicalLoadOutput.model_validate(mechanical_load_payload(adjustment_request=None))
    with pytest.raises(ValidationError):
        MechanicalLoadOutput.model_validate(mechanical_load_payload(plan_adjustment_needed=False))


def test_workout_adjustment_replace_requires_new_workout() -> None:
    with pytest.raises(ValidationError):
        WorkoutAdjustment.model_validate(
            {"workout_id": str(uuid.uuid4()), "action": "REPLACE", "reason": "x"}
        )


def test_nutrition_recovery_is_bipartite() -> None:
    out = NutritionRecoveryOutput.model_validate(nutrition_recovery_payload())
    assert out.nutrition_protocol.caffeine.cutoff_local_time == "14:00"
    assert out.recovery_protocol.readiness_next_session == "CAUTION"


def test_caffeine_cutoff_format() -> None:
    payload = nutrition_recovery_payload()
    payload["nutrition_protocol"]["caffeine"]["cutoff_local_time"] = "25:00"
    with pytest.raises(ValidationError):
        NutritionRecoveryOutput.model_validate(payload)


@pytest.mark.parametrize(
    "schema",
    [
        MechanicalLoadOutput,
        NutritionRecoveryOutput,
        PlanSkeletonOutput,
        BlockWorkoutsOutput,
        RefinementOutput,
        PlanAdjustmentOutput,
        CoachChatOutput,
    ],
)
def test_agent_outputs_export_json_schema(schema: type[BaseModel]) -> None:
    js = schema.model_json_schema()
    assert js["type"] == "object"
    assert js.get("additionalProperties") is False
