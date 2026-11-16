import gzip
import io
import zipfile

import pytest

from app.models.enums import Surface
from app.schemas.common import HrRange
from app.services.fit_files import InvalidFitFileError, extract_fit_bytes
from app.services.fit_parser import FitParseError, UnsupportedSportError, parse_fit
from tests.fit_builder import SPORT_CYCLING, build_fit, synthetic_run

MAX = 25 * 1024 * 1024


def test_summary_and_cadence_conversion() -> None:
    parsed = parse_fit(build_fit(synthetic_run(60, speed_mps=3.5, cadence_spm=176)))
    assert parsed.duration_s == 3600
    assert parsed.avg_pace_s_per_km == pytest.approx(1000 / 3.5, abs=1)
    # FIT stores strides/min: must be converted to steps/min
    assert parsed.avg_cadence_spm == pytest.approx(176, abs=1.5)
    assert parsed.avg_ground_contact_ms == pytest.approx(240, abs=2)
    assert parsed.avg_hr == pytest.approx(150, abs=1)
    assert parsed.surface is Surface.ASPHALT


def test_streams_are_downsampled_and_aligned() -> None:
    parsed = parse_fit(build_fit(synthetic_run(60)), max_points=1000)
    lengths = {len(v) for v in parsed.streams.values()}
    assert lengths == {1000}
    assert parsed.sample_count == 3600


def test_steady_run_no_breakdown() -> None:
    div = parse_fit(build_fit(synthetic_run(60))).computed.cadence_hr_divergence
    assert div.evaluated
    assert div.session_profile == "steady"
    assert not div.cadence_drop_detected
    assert not div.mechanical_breakdown


def test_cadence_drop_with_stable_hr_is_mechanical_breakdown() -> None:
    div = parse_fit(
        build_fit(synthetic_run(70, final_cadence_drop=6))
    ).computed.cadence_hr_divergence
    assert div.cadence_drop_spm == pytest.approx(6, abs=1)
    assert div.hr_stable
    assert div.mechanical_breakdown


def test_cadence_drop_with_cardiac_drift_is_not_pure_mechanical() -> None:
    div = parse_fit(
        build_fit(synthetic_run(70, final_cadence_drop=6, final_hr_rise=12))
    ).computed.cadence_hr_divergence
    assert div.cadence_drop_detected
    assert div.hr_stable is False
    assert not div.mechanical_breakdown


def test_target_zone_overrides_relative_stability() -> None:
    """HR rises 5% but stays inside the athlete's target zone → still mechanical."""
    fit = build_fit(synthetic_run(70, final_cadence_drop=6, final_hr_rise=8))
    raw = parse_fit(fit).computed.cadence_hr_divergence
    assert raw.hr_stable is False and not raw.mechanical_breakdown

    zoned = parse_fit(fit, target_hr=HrRange(min_bpm=145, max_bpm=162))
    assert zoned.computed.cadence_hr_divergence.hr_in_target_zone
    assert zoned.computed.cadence_hr_divergence.mechanical_breakdown


def test_ground_contact_rise_alone_triggers_breakdown() -> None:
    div = parse_fit(build_fit(synthetic_run(70, final_gct_rise=15))).computed.cadence_hr_divergence
    assert not div.cadence_drop_detected
    assert div.ground_contact_rise_detected
    assert div.mechanical_breakdown


def test_stride_length_collapse_with_stable_hr_is_breakdown() -> None:
    """NYC pattern: same cadence and HR, pace -20% → shorter stride → muscular breakdown."""
    div = parse_fit(
        build_fit(synthetic_run(70, final_speed_drop=0.7))
    ).computed.cadence_hr_divergence
    assert not div.cadence_drop_detected
    assert div.stride_length_change_pct is not None and div.stride_length_change_pct < -15
    assert div.stride_length_drop_detected and div.mechanical_breakdown


def test_stride_collapse_with_rising_hr_is_not_pure_mechanical() -> None:
    div = parse_fit(
        build_fit(synthetic_run(70, final_speed_drop=0.7, final_hr_rise=12))
    ).computed.cadence_hr_divergence
    assert div.stride_length_drop_detected and not div.mechanical_breakdown


def test_small_cadence_drop_below_threshold() -> None:
    div = parse_fit(
        build_fit(synthetic_run(70, final_cadence_drop=2))
    ).computed.cadence_hr_divergence
    assert not div.mechanical_breakdown


def test_short_run_not_evaluated() -> None:
    div = parse_fit(build_fit(synthetic_run(10))).computed.cadence_hr_divergence
    assert not div.evaluated
    assert div.reason


def test_trail_surface_from_sub_sport() -> None:
    assert parse_fit(build_fit(synthetic_run(30), sub_sport="trail")).surface is Surface.TRAIL


def test_summary_fallback_without_session_message() -> None:
    parsed = parse_fit(build_fit(synthetic_run(30), with_session=False))
    assert parsed.duration_s == pytest.approx(1799, abs=1)
    assert parsed.distance_m > 6000


def test_non_running_sport_rejected() -> None:
    with pytest.raises(UnsupportedSportError):
        parse_fit(build_fit(synthetic_run(30), sport=SPORT_CYCLING))


def test_corrupted_fit_rejected() -> None:
    data = bytearray(build_fit(synthetic_run(5)))
    data[-1] ^= 0xFF  # break the CRC
    with pytest.raises(FitParseError):
        parse_fit(bytes(data))


# --- Containers ---------------------------------------------------------------------------


def test_extract_raw_gzip_zip() -> None:
    fit = build_fit(synthetic_run(5))
    assert extract_fit_bytes(fit, MAX) == fit
    assert extract_fit_bytes(gzip.compress(fit), MAX) == fit

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "garmin export")
        zf.writestr("123456_ACTIVITY.fit", fit)
    assert extract_fit_bytes(buf.getvalue(), MAX) == fit


def test_extract_rejects_non_fit_and_bombs() -> None:
    with pytest.raises(InvalidFitFileError):
        extract_fit_bytes(b"<gpx></gpx>", MAX)
    with pytest.raises(InvalidFitFileError):
        extract_fit_bytes(gzip.compress(b"\0" * 2048), 1024)


def test_elevation_ignores_barometric_noise() -> None:
    import numpy as np
    import pandas as pd

    from app.services.fit_parser import _elevation

    rng = np.random.default_rng(1)
    flat = pd.DataFrame({"altitude": 40 + rng.normal(0, 0.4, 3000)})
    gain, loss = _elevation(flat)
    assert gain is not None and loss is not None
    assert gain < 3 and loss < 3

    hill = pd.DataFrame(
        {"altitude": np.concatenate([np.linspace(40, 90, 600), np.linspace(90, 40, 600)])}
    )
    gain, loss = _elevation(hill)
    assert gain == pytest.approx(50, abs=3) and loss == pytest.approx(50, abs=3)
