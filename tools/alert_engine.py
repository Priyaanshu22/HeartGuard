"""
alert_engine.py — Heart Guard V1
Layer: 1+2 → 3 (Processed Reading + Baseline → Alert Payload)
SOP: architecture/alert_engine_sop.md

IMMUTABLE RULES (from gemini.md):
- NEVER trigger from a single noisy reading
- NEVER skip activity context
- NEVER use population baselines
- NEVER use words: "heart attack", "diagnosis", "detect disease", "predict"
"""

import uuid
from datetime import datetime, timezone
from typing import Optional


# ─── Alert Status Tiers ───────────────────────────────────────────────────────
# Per gemini.md alert tier table. Do NOT change these without updating gemini.md first.
STATUS_TIERS = [
    {"tier": 0, "status": "normal",            "hr_std_min": 0.0, "hr_std_max": 2.0, "min_consecutive": 0},
    {"tier": 1, "status": "worth_noting",      "hr_std_min": 2.0, "hr_std_max": 3.0, "min_consecutive": 3},
    {"tier": 2, "status": "worth_watching",    "hr_std_min": 3.0, "hr_std_max": 4.0, "min_consecutive": 5},
    {"tier": 3, "status": "medical_attention", "hr_std_min": 4.0, "hr_std_max": 5.0, "min_consecutive": 7},
    {"tier": 4, "status": "sos",               "hr_std_min": 5.0, "hr_std_max": 999, "min_consecutive": 3},
]

# Extreme spike: bypass consecutive requirement entirely
EXTREME_SPIKE_THRESHOLD = 6.0

# Exercise relaxation multiplier: divide observed deviation by this before tier lookup
EXERCISE_RELAXATION_FACTOR = 1.5

DISCLAIMER = "This is a personal pattern alert, not a medical diagnosis."
SAMPLING_INTERVAL_SECONDS = 10  # Approximate seconds per reading for duration estimate


# ─── Internal Helpers ─────────────────────────────────────────────────────────

def _get_tier(adjusted_deviation: float) -> dict:
    """Return the tier dict for a given activity-adjusted HR deviation (std devs)."""
    for tier in reversed(STATUS_TIERS):
        if adjusted_deviation >= tier["hr_std_min"]:
            return tier
    return STATUS_TIERS[0]  # Normal


def _generate_explanation(
    status: str,
    hr_bpm: Optional[float],
    baseline_hr_mean: float,
    duration_minutes: float,
    activity_state: str,
    temp_deviation: Optional[float],
) -> str:
    """
    Generate a plain-English explanation. No banned words. No diagnosis.
    All values formatted for a lay user.
    """
    if status == "normal":
        return "Your readings are within your personal normal range."

    if status == "calibrating":
        return "Still learning your personal baseline. Check back soon."

    direction = "elevated" if (hr_bpm or 0) > baseline_hr_mean else "lower than usual"
    duration_str = f"approximately {round(duration_minutes, 1)} minutes" if duration_minutes > 1 else "a short time"
    activity_str = activity_state.replace("_", " ")

    explanation = (
        f"Your heart rate has been {direction} ({hr_bpm} bpm vs your personal "
        f"resting baseline of {round(baseline_hr_mean, 0):.0f} bpm) for {duration_str} "
        f"while you appear to be {activity_str}. This is unusual for you."
    )

    if temp_deviation is not None and abs(temp_deviation) >= 0.8:
        temp_dir = "higher" if temp_deviation > 0 else "lower"
        explanation += (
            f" Your temperature is also {abs(round(temp_deviation, 1))}°C "
            f"{temp_dir} than your usual baseline."
        )

    return explanation


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def evaluate(
    reading: dict,
    baseline: Optional[dict],
    anomaly_state: dict,
) -> tuple[dict, dict]:
    """
    Evaluate a Layer 1 reading against a Layer 2 baseline.
    Returns (layer3_alert_payload, updated_anomaly_state).

    anomaly_state shape:
    {
        "consecutive_anomalous_readings": int,
        "current_status": str,
        "status_start_time": str,
        "last_reading_time": str,
    }

    SOP reference: architecture/alert_engine_sop.md
    """
    now = datetime.now(timezone.utc).isoformat()
    derived = reading.get("derived", {})
    hr_bpm = derived.get("heart_rate_bpm")
    hr_confidence = derived.get("hr_confidence", 0.0)
    activity_state = derived.get("activity_state", "unknown")
    temp_celsius = derived.get("temperature_celsius")
    signal_quality = reading.get("signal_quality", "failed")

    user_id = reading.get("user_id", "unknown")
    timestamp = reading.get("timestamp", now)

    def _build_payload(
        status: str,
        triggered: bool,
        tier: int,
        hr_dev_std: Optional[float],
        hr_dev_pct: Optional[float],
        temp_dev: Optional[float],
        consecutive: int,
        explanation: str,
        sos_available: bool,
        baseline_hr_mean: Optional[float] = None,
    ) -> dict:
        duration_min = round(
            (consecutive * SAMPLING_INTERVAL_SECONDS) / 60.0, 2
        )
        severity = min(tier + (1 if (temp_dev or 0) >= 1.0 else 0), 5)
        return {
            "alert_id": str(uuid.uuid4()),
            "user_id": user_id,
            "timestamp": timestamp,
            "status": status,
            "triggered": triggered,
            "current_readings": {
                "heart_rate_bpm": hr_bpm,
                "activity_state": activity_state,
                "temperature_celsius": temp_celsius,
            },
            "baseline_comparison": {
                "hr_deviation_std": round(hr_dev_std, 4) if hr_dev_std is not None else None,
                "hr_deviation_percent": round(hr_dev_pct, 2) if hr_dev_pct is not None else None,
                "temp_deviation_celsius": round(temp_dev, 3) if temp_dev is not None else None,
                "activity_adjusted": activity_state in ("light_activity", "exercise"),
            },
            "pattern": {
                "duration_minutes": duration_min,
                "consecutive_anomalous_readings": consecutive,
                "severity_score": severity,
            },
            "explanation": explanation,
            "disclaimer": DISCLAIMER,
            "sos_available": sos_available,
        }

    # ── Step 1: Guard — Baseline Established ──────────────────────────────────
    if baseline is None or not baseline.get("baseline_established"):
        return (
            _build_payload(
                status="calibrating",
                triggered=False,
                tier=0,
                hr_dev_std=None,
                hr_dev_pct=None,
                temp_dev=None,
                consecutive=0,
                explanation="Still learning your personal baseline. Check back soon.",
                sos_available=False,
            ),
            anomaly_state,
        )

    resting_hr = baseline["resting_hr"]
    hr_mean = resting_hr["mean"]
    hr_std = resting_hr["std_dev"]  # Already floored at 0.1 in database layer

    # ── Step 2: Guard — Signal Quality ────────────────────────────────────────
    # Low quality = neutral (do not increment OR reset counter)
    if signal_quality not in ("good", "fair") or hr_confidence < 0.6 or hr_bpm is None:
        return (
            _build_payload(
                status=anomaly_state.get("current_status", "normal"),
                triggered=False,
                tier=0,
                hr_dev_std=None,
                hr_dev_pct=None,
                temp_dev=None,
                consecutive=anomaly_state.get("consecutive_anomalous_readings", 0),
                explanation="Reading quality insufficient for assessment. Counter unchanged.",
                sos_available=False,
            ),
            anomaly_state,  # State unchanged
        )

    # ── Step 3: Activity Gating & Baseline Selection ──────────────────────────
    if activity_state == "exercise" and baseline.get("exercise_hr") and baseline["exercise_hr"].get("mean"):
        hr_mean = baseline["exercise_hr"]["mean"]
        hr_std = max(float(baseline["exercise_hr"].get("std_dev", 10.0)), 0.1)
        relaxation = 1.0
    else:
        relaxation = EXERCISE_RELAXATION_FACTOR if activity_state in ("light_activity", "exercise") else 1.0

    # ── Step 4: HR Z-Score ────────────────────────────────────────────────────
    raw_hr_deviation = (hr_bpm - hr_mean) / hr_std
    adjusted_deviation = raw_hr_deviation / relaxation
    hr_dev_pct = ((hr_bpm - hr_mean) / hr_mean) * 100

    # ── Step 5: Temperature Deviation ─────────────────────────────────────────
    temp_deviation: Optional[float] = None
    if baseline.get("temperature") and temp_celsius is not None:
        temp_deviation = temp_celsius - baseline["temperature"]["mean"]

    # ── Step 6: Determine Tier ────────────────────────────────────────────────
    # Extreme single spike bypasses consecutive requirement (SOP Step 6, SOS rule)
    is_extreme_spike = abs(raw_hr_deviation) >= EXTREME_SPIKE_THRESHOLD

    current_tier = _get_tier(abs(adjusted_deviation))
    tier_number = current_tier["tier"]
    tier_status = current_tier["status"]
    min_consecutive = current_tier["min_consecutive"]

    # ── Step 7: Update Anomaly Counter ────────────────────────────────────────
    updated_state = dict(anomaly_state)
    updated_state["last_reading_time"] = now

    if tier_number == 0:
        # Normal reading → RESET counter
        updated_state["consecutive_anomalous_readings"] = 0
        updated_state["current_status"] = "normal"
        updated_state["status_start_time"] = now
    else:
        # Anomalous reading → increment
        updated_state["consecutive_anomalous_readings"] = (
            anomaly_state.get("consecutive_anomalous_readings", 0) + 1
        )
        if updated_state.get("current_status") == "normal":
            updated_state["status_start_time"] = now
        updated_state["current_status"] = tier_status

    consecutive = updated_state["consecutive_anomalous_readings"]

    # ── Determine if this actually triggers an alert ───────────────────────────
    triggered = (
        tier_number > 0
        and (consecutive >= min_consecutive or is_extreme_spike)
    )
    sos_available = tier_number >= 3

    # ── Step 9: Generate Explanation ─────────────────────────────────────────
    explanation = _generate_explanation(
        status=tier_status if triggered else "normal",
        hr_bpm=hr_bpm,
        baseline_hr_mean=hr_mean,
        duration_minutes=(consecutive * SAMPLING_INTERVAL_SECONDS) / 60.0,
        activity_state=activity_state,
        temp_deviation=temp_deviation,
    )

    # ── Step 10: Assemble Payload ─────────────────────────────────────────────
    payload = _build_payload(
        status=tier_status if triggered else "normal",
        triggered=triggered,
        tier=tier_number,
        hr_dev_std=abs(raw_hr_deviation),
        hr_dev_pct=hr_dev_pct,
        temp_dev=temp_deviation,
        consecutive=consecutive,
        explanation=explanation,
        sos_available=sos_available,
        baseline_hr_mean=hr_mean,
    )

    return payload, updated_state
