"""
signal_processor.py — Heart Guard V1
Layer: 0 → 1 (Raw Sensor Payload → Processed Reading)
SOP: architecture/signal_processor_sop.md
"""

import uuid
import math
import numpy as np
from datetime import datetime, timezone
from typing import Optional

try:
    import heartpy as hp
    HEARTPY_AVAILABLE = True
except ImportError:
    HEARTPY_AVAILABLE = False

try:
    from scipy.signal import filtfilt, butter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


# ─── Step 2: Butterworth Bandpass Filter ──────────────────────────────────────

def _bandpass_filter(signal: list[float], sampling_rate: float) -> np.ndarray:
    """
    Apply a zero-phase 4th-order Butterworth bandpass filter (0.5–12 Hz).
    Removes DC baseline wander and high-frequency noise from PPG signal.
    Must be called before any peak detection.
    """
    if not SCIPY_AVAILABLE:
        return np.array(signal)  # Pass through if scipy not installed

    nyquist = sampling_rate / 2.0
    low = 0.5 / nyquist
    high = min(12.0 / nyquist, 0.99)  # Cap below Nyquist
    b, a = butter(4, [low, high], btype="band")
    return filtfilt(b, a, np.array(signal))


# ─── Step 5: Activity State Classification ────────────────────────────────────

def _classify_activity(x: float, y: float, z: float) -> tuple[float, str]:
    """
    Classify activity state from raw accelerometer readings.
    Returns (activity_magnitude, activity_state).
    Invariant: Deterministic. No ML.
    """
    if x == 0.0 and y == 0.0 and z == 0.0:
        return 0.0, "unknown"

    magnitude = math.sqrt(x**2 + y**2 + z**2)
    activity_net = abs(magnitude - 9.8)  # Subtract gravity component

    if activity_net < 0.5:
        state = "resting"
    elif activity_net < 2.0:
        state = "light_activity"
    else:
        state = "exercise"

    return round(magnitude, 4), state


# ─── Step 6: Temperature Validation ───────────────────────────────────────────

def _validate_temperature(value: Optional[float]) -> Optional[float]:
    """
    Pass-through with physiological range check.
    Rejects values outside [30.0, 42.0]°C as hardware faults.
    """
    if value is None:
        return None
    if not (30.0 <= value <= 42.0):
        return None
    return round(value, 2)


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def process(payload: dict) -> dict:
    """
    Transform a Layer 0 raw sensor payload into a Layer 1 processed reading.
    Returns a fully populated Layer 1 dict. Never raises — always returns a result.

    SOP reference: architecture/signal_processor_sop.md
    """
    reading_id = str(uuid.uuid4())
    user_id = payload.get("user_id", "unknown")
    device_id = payload.get("device_id", "unknown")
    timestamp = payload.get("timestamp", datetime.now(timezone.utc).isoformat())

    sensor = payload.get("sensor", {})
    ppg = sensor.get("ppg", {})
    accel = sensor.get("accelerometer", {})
    temp_raw = sensor.get("temperature", {}).get("value_celsius")

    raw_signal = ppg.get("raw_signal", [])
    sampling_rate = ppg.get("sampling_rate_hz", 100)

    # ── Step 1: Input Validation ──────────────────────────────────────────────
    if len(raw_signal) < 50:
        return {
            "reading_id": reading_id,
            "user_id": user_id,
            "device_id": device_id,
            "timestamp": timestamp,
            "derived": {
                "heart_rate_bpm": None,
                "hr_confidence": 0.0,
                "temperature_celsius": _validate_temperature(temp_raw),
                "activity_magnitude": 0.0,
                "activity_state": "unknown",
            },
            "signal_quality": "rejected",
        }

    # ── Step 2: PPG Bandpass Filter ───────────────────────────────────────────
    filtered_signal = _bandpass_filter(raw_signal, float(sampling_rate))

    # ── Steps 3 & 4: Signal Quality + Heart Rate Extraction ───────────────────
    heart_rate_bpm: Optional[float] = None
    hr_confidence: float = 0.0
    signal_quality: str = "failed"

    if HEARTPY_AVAILABLE:
        try:
            working_data, measures = hp.process(
                filtered_signal,
                sample_rate=float(sampling_rate),
                report_time=False,
                calc_freq=False,
            )
            heart_rate_bpm = round(float(measures["bpm"]), 1)

            # Confidence proxy: ratio of valid inter-beat intervals (IBI)
            total_beats = len(working_data.get("peaklist", []))
            rejected_beats = len(working_data.get("removed_beats", []))
            if total_beats > 0:
                hr_confidence = round(1.0 - (rejected_beats / total_beats), 3)
                hr_confidence = max(0.0, min(1.0, hr_confidence))
            else:
                hr_confidence = 0.0

            if hr_confidence >= 0.8:
                signal_quality = "good"
            elif hr_confidence >= 0.6:
                signal_quality = "fair"
            else:
                signal_quality = "poor"

        except Exception:
            # HeartPy failed to process (too noisy, insufficient beats, etc.)
            heart_rate_bpm = None
            hr_confidence = 0.0
            signal_quality = "failed"
    else:
        # HeartPy not installed — degrade gracefully
        signal_quality = "failed"

    # ── Step 5: Activity State ────────────────────────────────────────────────
    activity_magnitude, activity_state = _classify_activity(
        accel.get("x", 0.0),
        accel.get("y", 0.0),
        accel.get("z", 0.0),
    )

    # ── Step 6: Temperature ───────────────────────────────────────────────────
    temperature_celsius = _validate_temperature(temp_raw)

    # ── Step 7: Assemble Output ───────────────────────────────────────────────
    return {
        "reading_id": reading_id,
        "user_id": user_id,
        "device_id": device_id,
        "timestamp": timestamp,
        "derived": {
            "heart_rate_bpm": heart_rate_bpm,
            "hr_confidence": hr_confidence,
            "temperature_celsius": temperature_celsius,
            "activity_magnitude": activity_magnitude,
            "activity_state": activity_state,
        },
        "signal_quality": signal_quality,
    }
