"""Deterministic .fit parser (fitparse + pandas) and running mechanics metrics.

Extracts the time series (timestamp, pace, heart_rate, cadence, elevation, ground_contact_time)
and computes the *Cadence vs HR Divergence*: in the final fraction of a long run / quality
session, HR stable (or within the athlete's target zone) while cadence drops more than
4 spm or ground contact time rises → mechanical (muscular) breakdown without cardiac drift.

No athlete-specific pace/HR is hardcoded: the only physiological input is the optional
`target_hr` range, derived upstream from the athlete's profile.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import fitparse  # type: ignore[import-untyped]
import numpy as np
import pandas as pd

from app.models.enums import Surface
from app.schemas.activity import CadenceHrDivergenceMetrics, ComputedMetrics, SegmentStats
from app.schemas.common import HrRange

RUNNING_SPORTS = {"running", "generic", None}

SUB_SPORT_SURFACE = {
    "trail": Surface.TRAIL,
    "treadmill": Surface.TREADMILL,
    "track": Surface.TRACK,
    "street": Surface.ASPHALT,
    "road": Surface.ASPHALT,
}

STREAM_COLUMNS = {
    "elapsed_s": "elapsed_s",
    "distance_m": "distance",
    "pace_s_per_km": "pace",
    "heart_rate": "heart_rate",
    "cadence_spm": "cadence",
    "elevation_m": "altitude",
    "ground_contact_ms": "gct",
}


class FitParseError(ValueError):
    pass


class UnsupportedSportError(ValueError):
    pass


@dataclass(frozen=True)
class DivergenceThresholds:
    final_fraction: float = 0.20  # last 20% of moving time
    baseline_start_fraction: float = 0.10  # skip warm-up
    baseline_end_fraction: float = 0.50
    cadence_drop_spm: float = 4.0  # spec: "oltre 4-5 passi/min"
    hr_stable_pct: float = 3.0
    ground_contact_rise_pct: float = 4.0
    min_moving_s: float = 20 * 60
    min_segment_samples: int = 30
    moving_speed_mps: float = 1.0
    max_gap_s: float = 5.0  # dt cap when accumulating moving time
    variable_speed_cv: float = 0.15  # above → intervals/fartlek: compare work samples only
    work_speed_quantile: float = 0.65


DEFAULT_THRESHOLDS = DivergenceThresholds()


@dataclass
class ParsedFit:
    sport: str | None
    sub_sport: str | None
    start_time: datetime
    duration_s: int
    moving_time_s: int | None
    distance_m: float
    avg_pace_s_per_km: float | None
    avg_hr: float | None
    max_hr: float | None
    avg_cadence_spm: float | None
    avg_ground_contact_ms: float | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    surface: Surface | None
    computed: ComputedMetrics
    sample_count: int
    streams: dict[str, list[float | None]] = field(default_factory=dict)


# --- Public API -------------------------------------------------------------------------


def parse_fit(
    data: bytes,
    *,
    target_hr: HrRange | None = None,
    thresholds: DivergenceThresholds = DEFAULT_THRESHOLDS,
    max_points: int = 3000,
) -> ParsedFit:
    try:
        fit = fitparse.FitFile(data)
        fit.parse()
    except fitparse.FitParseError as exc:  # base of CRC, EOF and header errors
        raise FitParseError(f"Unreadable FIT file: {exc}") from exc

    session = _session_values(fit)
    sport = _as_str(session.get("sport"))
    if sport not in RUNNING_SPORTS:
        raise UnsupportedSportError(f"Unsupported sport '{sport}': BRYT ingests running only")
    sub_sport = _as_str(session.get("sub_sport"))

    df = _records_frame(fit)
    if df.empty:
        raise FitParseError("FIT file contains no record messages")
    df = _normalize(df)

    moving = _moving(df, thresholds)
    start_time = _utc(session.get("start_time")) or _utc(df["timestamp"].iloc[0])
    assert start_time is not None
    elapsed = float(df["elapsed_s"].iloc[-1])
    session_elapsed = _num(session.get("total_elapsed_time"))
    duration_s = session_elapsed if session_elapsed is not None else elapsed
    moving_time = _coalesce(_num(session.get("total_timer_time")), _moving_time(moving, thresholds))
    distance = _coalesce(_num(session.get("total_distance")), _last(df["distance"])) or 0.0
    gain, loss = _elevation(df)

    computed = ComputedMetrics(
        moving_time_s=_round(_moving_time(moving, thresholds)),
        speed_cv=_round(_speed_cv(moving), 3),
        aerobic_decoupling_pct=_round(_aerobic_decoupling(moving)),
        cadence_hr_divergence=analyze_cadence_hr_divergence(df, target_hr, thresholds),
    )

    return ParsedFit(
        sport=sport,
        sub_sport=sub_sport,
        start_time=start_time,
        duration_s=int(round(duration_s)),
        moving_time_s=int(round(moving_time)) if moving_time else None,
        distance_m=round(float(distance), 1),
        avg_pace_s_per_km=_round(moving_time / (distance / 1000))
        if distance and moving_time
        else None,
        avg_hr=_round(_coalesce(_num(session.get("avg_heart_rate")), _mean(moving["heart_rate"]))),
        max_hr=_round(_coalesce(_num(session.get("max_heart_rate")), _max(df["heart_rate"]))),
        avg_cadence_spm=_round(_mean(moving["cadence"])),
        avg_ground_contact_ms=_round(_mean(moving["gct"])),
        elevation_gain_m=_round(_coalesce(_num(session.get("total_ascent")), gain)),
        elevation_loss_m=_round(_coalesce(_num(session.get("total_descent")), loss)),
        surface=SUB_SPORT_SURFACE.get(sub_sport or ""),
        computed=computed,
        sample_count=len(df),
        streams=_downsample(df, max_points),
    )


def analyze_cadence_hr_divergence(
    df: pd.DataFrame,
    target_hr: HrRange | None = None,
    thresholds: DivergenceThresholds = DEFAULT_THRESHOLDS,
) -> CadenceHrDivergenceMetrics:
    """`df` must be normalized (elapsed_s, speed, cadence in spm, heart_rate, gct, pace)."""
    th = thresholds
    moving = _moving(df, th)
    if moving["cadence"].notna().sum() == 0:
        return CadenceHrDivergenceMetrics(evaluated=False, reason="no cadence data")

    mt = moving["elapsed_s"].diff().clip(upper=th.max_gap_s).fillna(0).cumsum()
    total = float(mt.iloc[-1]) if len(mt) else 0.0
    if total < th.min_moving_s:
        return CadenceHrDivergenceMetrics(
            evaluated=False, reason=f"moving time {total:.0f}s below {th.min_moving_s:.0f}s"
        )

    variable = (_speed_cv(moving) or 0.0) > th.variable_speed_cv
    work = moving
    if variable:
        work = moving[moving["speed"] >= moving["speed"].quantile(th.work_speed_quantile)]
        mt = mt.loc[work.index]

    base = work[
        (mt >= th.baseline_start_fraction * total) & (mt < th.baseline_end_fraction * total)
    ]
    final = work[mt >= (1 - th.final_fraction) * total]
    profile = "variable" if variable else "steady"
    if len(base) < th.min_segment_samples or len(final) < th.min_segment_samples:
        return CadenceHrDivergenceMetrics(
            evaluated=False, reason="not enough samples in segments", session_profile=profile
        )

    b, f = _segment_stats(base), _segment_stats(final)
    cad_drop = _diff(b.cadence_spm, f.cadence_spm)
    hr_change = _diff(f.heart_rate, b.heart_rate)
    hr_change_pct = _pct(f.heart_rate, b.heart_rate)
    pace_change_pct = _pct(f.pace_s_per_km, b.pace_s_per_km)
    gct_change_pct = _pct(f.ground_contact_ms, b.ground_contact_ms)

    hr_stable = abs(hr_change_pct) <= th.hr_stable_pct if hr_change_pct is not None else None
    hr_in_zone = (
        target_hr.min_bpm <= f.heart_rate <= target_hr.max_bpm
        if target_hr is not None and f.heart_rate is not None
        else None
    )
    cadence_drop = cad_drop is not None and cad_drop > th.cadence_drop_spm
    gct_rise = gct_change_pct is not None and gct_change_pct >= th.ground_contact_rise_pct
    hr_ok = hr_in_zone if hr_in_zone is not None else bool(hr_stable)

    return CadenceHrDivergenceMetrics(
        evaluated=True,
        session_profile=profile,
        baseline=b,
        final=f,
        cadence_drop_spm=_round(cad_drop),
        hr_change_bpm=_round(hr_change),
        hr_change_pct=_round(hr_change_pct),
        pace_change_pct=_round(pace_change_pct),
        ground_contact_change_pct=_round(gct_change_pct),
        hr_stable=hr_stable,
        hr_in_target_zone=hr_in_zone,
        cadence_drop_detected=cadence_drop,
        ground_contact_rise_detected=gct_rise,
        mechanical_breakdown=(cadence_drop or gct_rise) and hr_ok,
    )


# --- FIT extraction ---------------------------------------------------------------------


def _session_values(fit: fitparse.FitFile) -> dict[str, Any]:
    for msg in fit.get_messages("session"):
        return dict(msg.get_values())
    return {}


def _records_frame(fit: fitparse.FitFile) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for msg in fit.get_messages("record"):
        v = msg.get_values()
        if v.get("timestamp") is None:
            continue
        cadence = v.get("cadence")
        if cadence is not None and v.get("fractional_cadence") is not None:
            cadence += v["fractional_cadence"]
        rows.append(
            {
                "timestamp": v["timestamp"],
                "heart_rate": v.get("heart_rate"),
                "cadence": cadence,
                "speed": _first(v, "enhanced_speed", "speed"),
                "altitude": _first(v, "enhanced_altitude", "altitude"),
                "distance": v.get("distance"),
                "gct": v.get("stance_time"),
            }
        )
    return pd.DataFrame(rows)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for col in ("heart_rate", "cadence", "speed", "altitude", "distance", "gct"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    df["elapsed_s"] = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()

    if df["speed"].isna().all() and df["distance"].notna().any():
        df["speed"] = (df["distance"].diff() / df["elapsed_s"].diff()).clip(lower=0)

    # Running cadence in FIT is strides/min (one foot): convert to steps/min
    moving_cad = df.loc[df["speed"] >= 1.0, "cadence"].dropna()
    if not moving_cad.empty and moving_cad.median() < 120:
        df["cadence"] = df["cadence"] * 2
    df.loc[df["cadence"] <= 0, "cadence"] = np.nan
    df.loc[df["heart_rate"] <= 0, "heart_rate"] = np.nan
    df.loc[df["gct"] <= 0, "gct"] = np.nan

    df["pace"] = np.where(df["speed"] >= 0.5, 1000 / df["speed"], np.nan)
    return df


def _moving(df: pd.DataFrame, th: DivergenceThresholds) -> pd.DataFrame:
    return df[df["speed"] >= th.moving_speed_mps]


def _moving_time(moving: pd.DataFrame, th: DivergenceThresholds) -> float:
    if moving.empty:
        return 0.0
    return float(moving["elapsed_s"].diff().clip(upper=th.max_gap_s).fillna(0).sum())


def _speed_cv(moving: pd.DataFrame) -> float | None:
    speed = moving["speed"].dropna()
    if len(speed) < 2 or speed.mean() == 0:
        return None
    return float(speed.std() / speed.mean())


def _aerobic_decoupling(moving: pd.DataFrame) -> float | None:
    data = moving[["speed", "heart_rate"]].dropna()
    if len(data) < 60:
        return None
    half = len(data) // 2
    first, second = data.iloc[:half], data.iloc[half:]
    ef1 = first["speed"].mean() / first["heart_rate"].mean()
    ef2 = second["speed"].mean() / second["heart_rate"].mean()
    return float((ef1 - ef2) / ef1 * 100)


def _elevation(df: pd.DataFrame) -> tuple[float | None, float | None]:
    return elevation_gain_loss(df["altitude"].dropna().tolist())


def elevation_gain_loss(
    altitudes: Sequence[float], hysteresis_m: float = 2.0
) -> tuple[float | None, float | None]:
    """Gain/loss with hysteresis: a climb or descent counts only once it exceeds
    `hysteresis_m`, so barometric/GPS noise on flat courses does not accumulate."""
    if len(altitudes) < 2:
        return None, None
    smooth = pd.Series(altitudes, dtype=float).rolling(5, center=True, min_periods=1).median()
    gain = loss = 0.0
    ref = float(smooth.iloc[0])
    for value in smooth:
        delta = float(value) - ref
        if delta >= hysteresis_m:
            gain, ref = gain + delta, float(value)
        elif delta <= -hysteresis_m:
            loss, ref = loss - delta, float(value)
    tail = float(smooth.iloc[-1]) - ref  # residual climb/descent shorter than the hysteresis
    return gain + max(tail, 0.0), loss + max(-tail, 0.0)


def _segment_stats(seg: pd.DataFrame) -> SegmentStats:
    return SegmentStats(
        start_s=round(float(seg["elapsed_s"].iloc[0]), 1),
        end_s=round(float(seg["elapsed_s"].iloc[-1]), 1),
        samples=len(seg),
        cadence_spm=_round(_median(seg["cadence"])),
        heart_rate=_round(_median(seg["heart_rate"])),
        pace_s_per_km=_round(_median(seg["pace"])),
        ground_contact_ms=_round(_median(seg["gct"])),
    )


def _downsample(df: pd.DataFrame, max_points: int) -> dict[str, list[float | None]]:
    cols = list(STREAM_COLUMNS.values())
    data = df[cols]
    if len(data) > max_points:
        bucket = (np.arange(len(data)) * max_points) // len(data)
        data = data.groupby(bucket).mean()
    return {
        name: [None if pd.isna(x) else round(float(x), 2) for x in data[col]]
        for name, col in STREAM_COLUMNS.items()
    }


# --- Small numeric helpers --------------------------------------------------------------


def _first(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if values.get(key) is not None:
            return values[key]
    return None


def _coalesce(primary: float | None, fallback: float | None) -> float | None:
    """Device value wins when present — including a legitimate 0."""
    return primary if primary is not None else fallback


def _as_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _utc(value: Any) -> datetime | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    ts = ts.tz_localize(UTC) if ts.tzinfo is None else ts.tz_convert(UTC)
    result: datetime = ts.to_pydatetime()
    return result


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _mean(series: pd.Series) -> float | None:
    s = series.dropna()
    return None if s.empty else float(s.mean())


def _median(series: pd.Series) -> float | None:
    s = series.dropna()
    return None if s.empty else float(s.median())


def _max(series: pd.Series) -> float | None:
    s = series.dropna()
    return None if s.empty else float(s.max())


def _last(series: pd.Series) -> float | None:
    s = series.dropna()
    return None if s.empty else float(s.iloc[-1])


def _diff(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a - b


def _pct(new: float | None, old: float | None) -> float | None:
    return None if new is None or old is None or old == 0 else (new - old) / old * 100


def _round(value: float | None, digits: int = 1) -> float | None:
    # + 0.0 normalizes -0.0
    return None if value is None else round(value, digits) + 0.0
