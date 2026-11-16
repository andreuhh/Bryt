"""Minimal valid payloads reused across tests."""

from typing import Any


def profile_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "background": "ROAD",
        "threshold_hr": 172,
        "max_hr": 190,
        "resting_hr": 45,
        "preferred_slot": "MORNING",
        "available_days": ["MON", "WED", "FRI", "SUN"],
        "work_type": "SEDENTARY",
        "terrain_access": ["ASPHALT", "TRAIL"],
        "weekly_volume_km": 60,
        "double_sessions_ok": True,
        "strength_sessions_per_week": 0,
        "strength_setting": "HOME",
    }
    return data | overrides


def mechanical_load_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "summary": "Lungo eseguito come da piano, cedimento meccanico negli ultimi 5 km.",
        "execution": {"compliance_score": 88, "notes": "Passo in linea con il target."},
        "mechanical_load": {
            "load_level": "HIGH",
            "load_score": 74,
            "surface_factor": 1.15,
            "eccentric_stress": "HIGH",
            "muscle_groups": ["quadriceps"],
            "explanation": "Asfalto veloce per un atleta con background trail.",
        },
        "cadence_hr_divergence": {
            "detected": True,
            "final_segment_start_pct": 80,
            "cadence_drop_spm": 6,
            "hr_change_bpm": 1,
            "interpretation": "FC stabile, cadenza in calo: cedimento meccanico.",
        },
        "false_alarm_suppressed": False,
        "alerts": [
            {
                "code": "MECHANICAL_BREAKDOWN",
                "severity": "WARNING",
                "title": "Cedimento meccanico",
                "message": "Cadenza -6 spm nel finale con FC stabile.",
            }
        ],
        "plan_adjustment_needed": True,
        "adjustment_request": {
            "reason": "Stress eccentrico elevato",
            "days_affected": 3,
            "guidance": "Sostituire la qualità di domani con un easy su sterrato.",
        },
    }
    return data | overrides


def nutrition_recovery_payload() -> dict[str, Any]:
    return {
        "summary": "Priorità a riparazione muscolare e glicogeno.",
        "nutrition_protocol": {
            "daily_carbs_g_per_kg": 7,
            "daily_protein_g_per_kg": 1.8,
            "post_session": {"window_minutes": 45, "carbs_g": 90, "protein_g": 30},
            "electrolytes": {"sodium_mg": 800, "fluids_ml": 1200},
            "caffeine": {
                "recommended": True,
                "dose_mg_per_kg": 3,
                "minutes_before_session": 60,
                "cutoff_local_time": "14:00",
            },
        },
        "recovery_protocol": {
            "readiness_next_session": "CAUTION",
            "sleep": {"target_hours": 8.5, "bedtime_local": "22:30"},
            "mobility": [{"name": "Foam roller quadricipiti", "duration_min": 10, "focus": "quad"}],
        },
    }
