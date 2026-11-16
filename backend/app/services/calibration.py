"""Athlete calibration: training zones derived from PBs, threshold HR and background.

Nothing here is an absolute pace or HR: every number is a ratio applied to the athlete's own
threshold pace (estimated from recent PBs) and threshold HR.

- Threshold pace ≈ pace sustainable for ~60 minutes, projected from each PB with Riegel's
  formula T2 = T1 · (D2/D1)^1.06. Older PBs are not discarded but penalized: +0.4% pace per
  month beyond 6 months (max +8%). Marathons alone underestimate athletes whose limit is
  muscular endurance, so a fast but older 10k can still be the best estimate.
- Zones follow Joe Friel's run zones (% of threshold HR / % of threshold pace), plus a
  'DT' zone for Norwegian double-threshold sessions (controlled, below LT2).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.models import PersonalBest, UserLifestyleProfile
from app.models.enums import CalibrationConfidence, Surface
from app.schemas.common import HrRange, PaceRange
from app.schemas.training import AthleteCalibration, TrainingZone

RIEGEL_EXPONENT = 1.06
THRESHOLD_DURATION_S = 3600
MIN_PB_DISTANCE_M = 1500  # Riegel is unreliable for sprints
AGE_GRACE_MONTHS = 6
AGE_PENALTY_PER_MONTH = 0.004
AGE_PENALTY_MAX = 0.08
FLAT_SURFACES = {Surface.ASPHALT, Surface.TRACK, Surface.TREADMILL}
LTHR_FROM_MAX_HR = 0.90  # fallback estimate when threshold HR is unknown


@dataclass(frozen=True)
class _ZoneSpec:
    code: str
    label: str
    hr_pct: tuple[float, float]  # % of threshold HR
    pace_pct: tuple[float, float]  # % of threshold pace (time per km): fast, slow


ZONES: tuple[_ZoneSpec, ...] = (
    _ZoneSpec("Z1", "Recupero", (0.70, 0.84), (1.30, 1.50)),
    _ZoneSpec("Z2", "Aerobico / easy", (0.85, 0.89), (1.14, 1.29)),
    _ZoneSpec("Z3", "Tempo / medio", (0.90, 0.94), (1.06, 1.13)),
    _ZoneSpec("DT", "Double threshold (sotto LT2)", (0.88, 0.95), (1.02, 1.08)),
    _ZoneSpec("Z4", "Soglia (LT2)", (0.95, 0.99), (0.99, 1.05)),
    _ZoneSpec("Z5", "VO2max", (1.00, 1.06), (0.90, 0.98)),
)


def riegel_threshold_pace(pb: PersonalBest) -> float:
    """Pace (s/km) the PB predicts for a ~60-minute effort."""
    distance_60 = pb.distance_m * (THRESHOLD_DURATION_S / pb.time_s) ** (1 / RIEGEL_EXPONENT)
    return float(THRESHOLD_DURATION_S / (distance_60 / 1000))


def age_adjusted_threshold_pace(pb: PersonalBest, today: date) -> float:
    months = (today - pb.achieved_on).days / 30.44
    penalty = min(max(months - AGE_GRACE_MONTHS, 0) * AGE_PENALTY_PER_MONTH, AGE_PENALTY_MAX)
    return riegel_threshold_pace(pb) * (1 + penalty)


def _confidence(pb: PersonalBest, today: date, flat: bool) -> CalibrationConfidence:
    months = (today - pb.achieved_on).days / 30.44
    if not flat or months > 12:
        return CalibrationConfidence.LOW
    return (
        CalibrationConfidence.HIGH if months <= AGE_GRACE_MONTHS else CalibrationConfidence.MEDIUM
    )


def compute_calibration(
    profile: UserLifestyleProfile, pbs: Sequence[PersonalBest], today: date
) -> AthleteCalibration:
    candidates = [pb for pb in pbs if pb.distance_m >= MIN_PB_DISTANCE_M]
    flat = [pb for pb in candidates if pb.surface in FLAT_SURFACES]
    usable = flat or candidates
    threshold_pace: float | None = None
    confidence = CalibrationConfidence.LOW
    source = "nessun PB utilizzabile (≥ 1500 m)"
    if usable:
        best = min(usable, key=lambda pb: age_adjusted_threshold_pace(pb, today))
        threshold_pace = age_adjusted_threshold_pace(best, today)
        confidence = _confidence(best, today, flat=bool(flat))
        months = (today - best.achieved_on).days / 30.44
        source = (
            f"riferimento {best.distance_m} m in {best.time_s} s ({best.achieved_on.isoformat()}, "
            f"{months:.0f} mesi fa) proiettato a 60' (Riegel)"
            + (
                f", penalità età +{(threshold_pace / riegel_threshold_pace(best) - 1):.1%}"
                if threshold_pace > riegel_threshold_pace(best)
                else ""
            )
            + ("" if flat else "; solo PB su terreni non piani: stima meno precisa")
        )

    threshold_hr = profile.threshold_hr
    if threshold_hr is None and profile.max_hr is not None:
        threshold_hr = round(profile.max_hr * LTHR_FROM_MAX_HR)
        source += f"; FC soglia stimata come {LTHR_FROM_MAX_HR:.0%} della FC max"
    elif threshold_hr is None:
        source += "; FC soglia e FC max assenti: zone FC non disponibili"

    zones = [
        TrainingZone(
            code=z.code,
            label=z.label,
            hr=HrRange(
                min_bpm=round(threshold_hr * z.hr_pct[0]),
                max_bpm=round(threshold_hr * z.hr_pct[1]),
            )
            if threshold_hr
            else None,
            pace=PaceRange(
                fast_s_per_km=round(threshold_pace * z.pace_pct[0], 1),
                slow_s_per_km=round(threshold_pace * z.pace_pct[1], 1),
            )
            if threshold_pace
            else None,
        )
        for z in ZONES
    ]
    return AthleteCalibration(
        confidence=confidence,
        threshold_pace_s_per_km=round(threshold_pace, 1) if threshold_pace else None,
        threshold_hr=threshold_hr,
        zones=zones,
        source_notes=source,
    )
