"""Domain enums shared by SQLModel tables and Pydantic schemas.

Persisted as VARCHAR (not native PG enums): adding a value never requires an ALTER TYPE.
"""

from enum import StrEnum


class AthleteBackground(StrEnum):
    ROAD = "ROAD"
    TRAIL = "TRAIL"
    TRACK = "TRACK"  # pista / mezzofondo


class TrainingSlot(StrEnum):
    MORNING = "MORNING"
    LUNCH = "LUNCH"
    EVENING = "EVENING"


class Weekday(StrEnum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"
    SAT = "SAT"
    SUN = "SUN"


class WorkType(StrEnum):
    SEDENTARY = "SEDENTARY"
    PHYSICAL = "PHYSICAL"


class StrengthSetting(StrEnum):
    NONE = "NONE"  # no strength work possible
    HOME = "HOME"  # bodyweight, dumbbells, kettlebell
    GYM = "GYM"


class HrSensor(StrEnum):
    CHEST_STRAP = "CHEST_STRAP"
    WRIST_OPTICAL = "WRIST_OPTICAL"


class DataCoverage(StrEnum):
    HIGH = "HIGH"  # recorded history reflects the athlete's real volume
    LOW = "LOW"  # sparse history: rely on the declared weekly volume


class Surface(StrEnum):
    ASPHALT = "ASPHALT"
    TRAIL = "TRAIL"
    TRACK = "TRACK"
    TREADMILL = "TREADMILL"
    GRAVEL = "GRAVEL"
    MIXED = "MIXED"


class SurfaceSource(StrEnum):
    """Where an activity's surface comes from (how much the agents can trust it)."""

    USER = "USER"  # tagged by the athlete
    DEVICE = "DEVICE"  # watch activity mode in the .fit (trail, track, treadmill, road)
    PROFILE_DEFAULT = "PROFILE_DEFAULT"  # generic "Run" → athlete's usual surface (probable)


class Methodology(StrEnum):
    TRADITIONAL = "TRADITIONAL"
    DOUBLE_THRESHOLD = "DOUBLE_THRESHOLD"  # scuola norvegese
    BLOCK = "BLOCK"  # periodizzazione a blocchi


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"  # background generation in progress
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


class BlockPhase(StrEnum):
    BASE = "BASE"
    BUILD = "BUILD"
    SPECIFIC = "SPECIFIC"
    PEAK = "PEAK"
    TAPER = "TAPER"
    TRANSITION = "TRANSITION"


class WeekLoadType(StrEnum):
    LOAD = "LOAD"
    DELOAD = "DELOAD"
    RACE = "RACE"


class WorkoutType(StrEnum):
    EASY = "EASY"
    RECOVERY = "RECOVERY"
    LONG = "LONG"
    THRESHOLD = "THRESHOLD"
    INTERVALS = "INTERVALS"
    TEMPO = "TEMPO"
    HILLS = "HILLS"
    RACE_PACE = "RACE_PACE"
    RACE = "RACE"
    STRENGTH = "STRENGTH"
    REST = "REST"


class WorkoutStatus(StrEnum):
    PLANNED = "PLANNED"
    COMPLETED = "COMPLETED"
    MODIFIED = "MODIFIED"


class WorkoutDetail(StrEnum):
    CONFIRMED = "CONFIRMED"  # next ~2 weeks: full structure, calibrated pace/HR
    PROVISIONAL = "PROVISIONAL"  # further ahead: type, volume and zones only


class RevisionStatus(StrEnum):
    APPLIED = "APPLIED"  # part of the workout history
    PENDING = "PENDING"  # proposal waiting for the athlete
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"  # replaced by a newer proposal or no longer applicable


class RevisionSource(StrEnum):
    WEEKLY_REFINEMENT = "WEEKLY_REFINEMENT"
    POST_ACTIVITY = "POST_ACTIVITY"
    COACH_CHAT = "COACH_CHAT"


class SessionSlot(StrEnum):
    SINGLE = "SINGLE"
    AM = "AM"  # double threshold: sessione mattina
    PM = "PM"  # double threshold: sessione sera


class StepKind(StrEnum):
    WARMUP = "WARMUP"
    WORK = "WORK"
    RECOVERY = "RECOVERY"
    COOLDOWN = "COOLDOWN"


class ActivitySource(StrEnum):
    INTERVALS = "INTERVALS"
    MANUAL_UPLOAD = "MANUAL_UPLOAD"


class AgentName(StrEnum):
    TRAINING_PERIODIZATION = "TRAINING_PERIODIZATION"
    MECHANICAL_LOAD = "MECHANICAL_LOAD"
    NUTRITION_RECOVERY = "NUTRITION_RECOVERY"
    COACH_CHAT = "COACH_CHAT"


class AgentTrigger(StrEnum):
    ONBOARDING = "ONBOARDING"
    POST_ACTIVITY = "POST_ACTIVITY"
    ADJUSTMENT = "ADJUSTMENT"
    CHAT = "CHAT"
    WEEKLY_REFINEMENT = "WEEKLY_REFINEMENT"


class AgentRunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class Feedback(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class CalibrationConfidence(StrEnum):
    HIGH = "HIGH"  # flat PB within 6 months
    MEDIUM = "MEDIUM"  # within 12 months
    LOW = "LOW"  # older, non-flat or missing → schedule a test to recalibrate


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AnalysisDepth(StrEnum):
    FULL = "FULL"  # MechanicalLoadAgent on its own model (Opus)
    LIGHT = "LIGHT"  # easy run without red flags: short note on the light model (Haiku)
