"""Athlete calibration: training zones derived from PBs, threshold HR and background.

Nothing here is an absolute pace or HR: every number is a ratio applied to the athlete's own
threshold pace (estimated from recent PBs) and threshold HR.

- Threshold pace ≈ pace sustainable for ~60 minutes, projected from each PB with Riegel's
  formula T2 = T1 · (D2/D1)^1.06. Recent (≤ 12 months) flat PBs are preferred.
- Zones follow Joe Friel's run zones (% of threshold HR / % of threshold pace), plus a
  'DT' zone for Norwegian double-threshold sessions (controlled, below LT2).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.models import PersonalBest, UserLifestyleProfile
from app.models.enums import Surface
from app.schemas.common import HrRange, PaceRange
from app.schemas.training import AthleteCalibration, TrainingZone

RIEGEL_EXPONENT = 1.06
THRESHOLD_DURATION_S = 3600
MIN_PB_DISTANCE_M = 1500  # Riegel is unreliable for sprints
PB_RECENCY = timedelta(days=365)
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


def _usable_pbs(pbs: Sequence[PersonalBest], today: date) -> tuple[list[PersonalBest], str]:
    candidates = [pb for pb in pbs if pb.distance_m >= MIN_PB_DISTANCE_M]
    flat = [pb for pb in candidates if pb.surface in FLAT_SURFACES]
    recent_flat = [pb for pb in flat if today - pb.achieved_on <= PB_RECENCY]
    for group, note in (
        (recent_flat, "PB su strada/pista degli ultimi 12 mesi"),
        (flat, "PB su strada/pista più vecchi di 12 mesi: forma attuale incerta"),
        (candidates, "solo PB su terreni non piani: stima meno precisa"),
    ):
        if group:
            return group, note
    return [], "nessun PB utilizzabile (≥ 1500 m)"


def compute_calibration(
    profile: UserLifestyleProfile, pbs: Sequence[PersonalBest], today: date
) -> AthleteCalibration:
    usable, pb_note = _usable_pbs(pbs, today)
    threshold_pace: float | None = None
    source = pb_note
    if usable:
        best = min(usable, key=riegel_threshold_pace)
        threshold_pace = riegel_threshold_pace(best)
        source = (
            f"{pb_note}; riferimento {best.distance_m} m in {best.time_s} s "
            f"({best.achieved_on.isoformat()}) proiettato a 60' (Riegel)"
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
        threshold_pace_s_per_km=round(threshold_pace, 1) if threshold_pace else None,
        threshold_hr=threshold_hr,
        zones=zones,
        source_notes=source,
    )
