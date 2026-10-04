"""
validate_pipeline.py — Heart Guard V1 Phase 3 Validation
Tests signal_processor and alert_engine across all 5 simulator scenarios.
Run: python validate_pipeline.py
"""
import sys
import json
sys.path.insert(0, ".")

from tools import signal_processor, alert_engine
from tools.simulator import generate_payload, SCENARIOS

PASS = "✅ PASS"
FAIL = "❌ FAIL"

errors = []

print("=" * 65)
print("  HEART GUARD V1 — PHASE 3 PIPELINE VALIDATION")
print("=" * 65)
print()

# ── Layer 0 → 1: Signal Processor ─────────────────────────────────────────────
print("─── LAYER 0 → 1: Signal Processor ────────────────────────────")
print()

results = {}
for name, scenario in SCENARIOS.items():
    desc = scenario["description"]
    kwargs = {k: v for k, v in scenario.items() if k != "description"}
    payload = generate_payload(user_id="test_user", **kwargs)
    reading = signal_processor.process(payload)
    derived = reading["derived"]
    results[name] = reading

    quality = reading["signal_quality"]
    hr = derived["heart_rate_bpm"]
    conf = derived["hr_confidence"]
    act = derived["activity_state"]
    temp = derived["temperature_celsius"]

    print(f"  Scenario     : {name}")
    print(f"  Description  : {desc}")
    print(f"  Signal Qual  : {quality}")
    print(f"  HR (bpm)     : {hr}")
    print(f"  HR Confidence: {conf}")
    print(f"  Activity     : {act}  (mag={derived['activity_magnitude']})")
    print(f"  Temperature  : {temp}")

    # Assertions
    assert "reading_id" in reading, "Missing reading_id"
    assert reading["user_id"] == "test_user", "user_id mismatch"
    assert quality in ("good", "fair", "poor", "failed", "rejected"), f"Bad signal_quality: {quality}"
    assert act in ("resting", "light_activity", "exercise", "unknown"), f"Bad activity_state: {act}"

    # Scenario-specific checks
    if name == "normal_resting":
        assert quality in ("good", "fair"), f"Expected good/fair for clean signal, got {quality}"
        assert act == "resting", f"Expected resting, got {act}"
    if name == "exercise_normal":
        assert act == "exercise", f"Expected exercise, got {act}"
    if name == "noisy_signal":
        assert quality in ("poor", "failed"), f"Noisy signal should be poor/failed, got {quality}"

    print(f"  Assertions   : {PASS}")
    print()

# ── Alert Engine: No Baseline (calibrating guard) ─────────────────────────────
print("─── Alert Engine: No Baseline (all should return 'calibrating') ──")
print()

default_state = {
    "consecutive_anomalous_readings": 0,
    "current_status": "normal",
    "status_start_time": None,
    "last_reading_time": None,
}

for name, reading in results.items():
    alert, new_state = alert_engine.evaluate(reading, None, dict(default_state))
    status = alert["status"]
    triggered = alert["triggered"]
    ok = status == "calibrating" and triggered is False
    marker = PASS if ok else FAIL
    print(f"  {marker} {name}: status={status}, triggered={triggered}")
    if not ok:
        errors.append(f"[calibrating guard] {name}: expected status=calibrating, got {status}")

print()

# ── Alert Engine: With synthetic baseline (established) ───────────────────────
print("─── Alert Engine: Synthetic Baseline (established) ───────────")
print()

synthetic_baseline = {
    "user_id": "test_user",
    "computed_at": "2026-09-17T00:00:00+00:00",
    "sample_count": 150,
    "baseline_established": True,
    "resting_hr": {
        "mean": 68.0,
        "std_dev": 5.2,
        "p5": 58.0,
        "p95": 78.0,
    },
    "exercise_hr": {
        "mean": 130.0,
        "std_dev": 12.0,
    },
    "temperature": {
        "mean": 36.7,
        "std_dev": 0.3,
    },
}

expected_outcomes = {
    # Scenario name: (should_trigger_eventually, expected_status_when_triggered)
    "normal_resting":   (False, "normal"),
    "elevated_resting": (True,  "medical_attention"),  # 112 bpm vs 68 baseline = ~8.5 std dev
    "exercise_normal":  (False, "normal"),             # activity gating relaxes it
    "noisy_signal":     (False, "normal"),             # poor quality → skipped
    "extreme_spike":    (True,  "sos"),               # 180 bpm vs 68 baseline = extreme
}

# Simulate 10 consecutive readings of each scenario to build up counter
for name, reading in results.items():
    state = dict(default_state)
    last_alert = None
    for i in range(10):
        alert, state = alert_engine.evaluate(reading, synthetic_baseline, state)
        last_alert = alert

    should_trigger, exp_status = expected_outcomes[name]
    actually_triggered = last_alert["triggered"]
    actual_status = last_alert["status"]

    if should_trigger:
        ok = actually_triggered is True
        detail = f"triggered={actually_triggered}, status={actual_status} (expected ~{exp_status})"
    else:
        ok = actually_triggered is False
        detail = f"triggered={actually_triggered}, status={actual_status}"

    marker = PASS if ok else FAIL
    print(f"  {marker} {name}: {detail}")
    if not ok:
        errors.append(f"[alert logic] {name}: {detail}")

print()

# ── Banner ────────────────────────────────────────────────────────────────────
print("=" * 65)
if errors:
    print(f"  {FAIL} {len(errors)} FAILURE(S):")
    for e in errors:
        print(f"    - {e}")
    sys.exit(1)
else:
    print("  ✅ ALL TESTS PASSED — Pipeline is valid.")
    print()
    print("  Layer 0 → 1 (signal_processor): OK")
    print("  Layer 1+2 → 3 (alert_engine):   OK")
    print("  Calibrating guard:               OK")
    print("  Activity gating:                 OK")
    print("  Consecutive anomaly counter:     OK")
print("=" * 65)
