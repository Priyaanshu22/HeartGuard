"""
baseline_engine.py — Heart Guard V1
Layer: 1 → 2 (Processed Readings → Personal Baseline Profile)
SOP: architecture/baseline_engine_sop.md
"""

import numpy as np
from datetime import datetime, timezone
from typing import Optional

from tools import database


# ─── Minimum sample count before baseline is "established" ───────────────────
MIN_RESTING_READINGS = 100
MIN_EXERCISE_READINGS = 20
MIN_TEMP_READINGS = 20


async def compute_baseline(user_id: str) -> dict:
    """
    Compute and persist the personal baseline profile for a user.
    Pulls the last 7 days of clean resting readings from the DB.
    Returns the baseline dict (also saves it to DB).

    SOP reference: architecture/baseline_engine_sop.md
    """
    # ── Step 1: Data Pull ─────────────────────────────────────────────────────
    all_readings = await database.get_recent_readings(user_id, hours=168)

    # ── Filter: clean resting readings for HR baseline ─────────────────────────
    resting_readings = [
        r for r in all_readings
        if r.get("activity_state") == "resting"
        and r.get("signal_quality") in ("good", "fair")
        and r.get("heart_rate_bpm") is not None
        and (r.get("hr_confidence") or 0.0) >= 0.6
    ]

    # ── Filter: exercise readings (optional) ───────────────────────────────────
    exercise_readings = [
        r for r in all_readings
        if r.get("activity_state") in ("light_activity", "exercise")
        and r.get("signal_quality") in ("good", "fair")
        and r.get("heart_rate_bpm") is not None
        and (r.get("hr_confidence") or 0.0) >= 0.6
    ]

    # ── Filter: temperature readings ───────────────────────────────────────────
    temp_readings = [
        r["temperature_celsius"]
        for r in all_readings
        if r.get("temperature_celsius") is not None
    ]

    sample_count = len(resting_readings)

    # ── Step 2: Sufficiency Check ─────────────────────────────────────────────
    baseline = {
        "user_id": user_id,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": sample_count,
        "baseline_established": False,
        "resting_hr": None,
        "exercise_hr": None,
        "temperature": None,
    }

    if sample_count < MIN_RESTING_READINGS:
        await database.save_baseline(baseline)
        return baseline

    # ── Step 3: Heart Rate Statistics ─────────────────────────────────────────
    hr_values = np.array([r["heart_rate_bpm"] for r in resting_readings], dtype=float)
    resting_hr_std = float(np.std(hr_values))

    # Invariant: floor std_dev at 0.1 to prevent division-by-zero in alert engine
    resting_hr_std = max(resting_hr_std, 0.1)

    baseline["resting_hr"] = {
        "mean": round(float(np.mean(hr_values)), 2),
        "std_dev": round(resting_hr_std, 4),
        "p5": round(float(np.percentile(hr_values, 5)), 2),
        "p95": round(float(np.percentile(hr_values, 95)), 2),
    }

    # ── Step 4: Exercise HR (optional) ────────────────────────────────────────
    if len(exercise_readings) >= MIN_EXERCISE_READINGS:
        ex_hr = np.array([r["heart_rate_bpm"] for r in exercise_readings], dtype=float)
        baseline["exercise_hr"] = {
            "mean": round(float(np.mean(ex_hr)), 2),
            "std_dev": round(max(float(np.std(ex_hr)), 0.1), 4),
        }

    # ── Step 5: Temperature Statistics ────────────────────────────────────────
    if len(temp_readings) >= MIN_TEMP_READINGS:
        temp_arr = np.array(temp_readings, dtype=float)
        baseline["temperature"] = {
            "mean": round(float(np.mean(temp_arr)), 3),
            "std_dev": round(max(float(np.std(temp_arr)), 0.01), 4),
        }

    # ── Step 6: Mark established & upsert ─────────────────────────────────────
    baseline["baseline_established"] = True
    await database.save_baseline(baseline)
    return baseline


async def recompute_all() -> None:
    """
    Recompute baselines for every known user. Called at startup and every 24h.
    """
    user_ids = await database.get_all_user_ids()
    for user_id in user_ids:
        try:
            await compute_baseline(user_id)
        except Exception as e:
            # Log but do not crash — one user failure should not block others
            print(f"[baseline_engine] ERROR recomputing baseline for {user_id}: {e}")
