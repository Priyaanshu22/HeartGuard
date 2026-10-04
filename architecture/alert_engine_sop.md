# 🚨 SOP: Alert Engine
> **Layer:** 1+2 → 3 — Processed Reading + Baseline → Alert Payload
> **Tool:** `tools/alert_engine.py`
> **Last Updated:** 2026-09-17
> **Status:** ✅ Active

---

## 🎯 Goal
Evaluate each incoming processed reading against the user's personal baseline. Determine if a pattern of anomaly exists, compute severity, and produce a human-readable **Layer 3 Alert Payload** when a threshold is crossed.

---

## 📥 Input
1. **Layer 1 reading** — current processed reading dict
2. **Layer 2 baseline** — user's baseline profile dict
3. **Anomaly counter state** — in-memory state per user: `consecutive_anomalous_readings`, `current_status`, `status_start_time`

---

## 📤 Output
**Layer 3 Alert Payload** (see `gemini.md`) — always returned. `triggered = False` if status is `normal`.

---

## ⚙️ Evaluation Pipeline

### Step 1: Guard — Baseline Established?
- Check `baseline.baseline_established == True`.
- If `False`: Return `status: "calibrating"`, `triggered: False`. Do not proceed.

### Step 2: Guard — Signal Quality
- Check `reading.signal_quality in ("good", "fair")` AND `reading.hr_confidence >= 0.6`.
- If fails: discard reading from anomaly counter logic. Return `triggered: False` with note `"low_quality_reading_skipped"`.
- **CRITICAL:** Low quality readings do NOT increment the anomaly counter, but they do NOT reset it either. They are neutral.

### Step 3: Activity Gating
- If `reading.activity_state == "exercise"`:
  - Apply **relaxed HR threshold multiplier: 1.5x std dev multipliers**.
  - This means a 3 std-dev deviation during exercise is treated as 2 std-dev (exercise elevation is expected).
  - Temperature anomaly checking proceeds normally regardless of activity state.
- If `reading.activity_state == "unknown"`:
  - Treat as `resting` (conservative — better to have false positive than false negative).

### Step 4: Heart Rate Z-Score
- Compute: `hr_deviation_std = (reading.heart_rate_bpm - baseline.resting_hr_mean) / baseline.resting_hr_std`
- Apply activity gate multiplier from Step 3.
- Compute: `hr_deviation_percent = ((reading.heart_rate_bpm - baseline.resting_hr_mean) / baseline.resting_hr_mean) * 100`

### Step 5: Temperature Deviation
- If `baseline.temp_mean` is not null AND `reading.temperature_celsius` is not null:
  - `temp_deviation_celsius = reading.temperature_celsius - baseline.temp_mean`
- Else: `temp_deviation_celsius = null`, temperature comparison skipped.

### Step 6: Determine Tier (The Core Decision)
Use HR z-score (activity-adjusted) as primary signal:

| Tier | Status | HR Std Dev Threshold | Min Duration (consecutive readings) |
|------|--------|---------------------|-------------------------------------|
| 0 | `normal` | < 2.0 | — |
| 1 | `worth_noting` | 2.0–3.0 | ≥ 3 readings |
| 2 | `worth_watching` | 3.0–4.0 | ≥ 5 readings |
| 3 | `medical_attention` | 4.0–5.0 | ≥ 7 readings |
| 4 | `sos` | > 5.0 | ≥ 3 readings OR single spike > 6.0 std dev |

> **Duration is proxied by consecutive anomalous readings** at V1 sampling frequency.
> Approximate: `duration_minutes ≈ consecutive_readings × (sampling_interval_seconds / 60)`

**Temperature modifier:** If `temp_deviation_celsius > 1.0°C` above baseline, bump severity score +1 (does not change tier directly but included in `severity_score`).

### Step 7: Update Anomaly Counter (Stateful — In-Memory)
- If this reading is anomalous (above Tier 0 threshold): `consecutive_anomalous_readings += 1`
- If this reading is normal (Tier 0): **RESET** `consecutive_anomalous_readings = 0` AND `current_status = "normal"`
- **Low quality readings:** No change to counter (Step 2 guard).

### Step 8: Compute Severity Score (1–5)
```
severity_score = tier_number
if temp_deviation_celsius > 1.0: severity_score += 1
severity_score = min(severity_score, 5)
```

### Step 9: Generate Explanation (Plain English)
Template (fill with real values):
```
"Your heart rate has been [elevated/low] ([X] bpm vs your resting baseline of [mean] bpm)
for approximately [N] minutes while you appear to be [activity_state].
This is [unusual for you / outside your normal range]."
```
- **NEVER** use: "heart attack", "diagnosis", "detect disease", "predict".
- Always append disclaimer: `"This is a personal pattern alert, not a medical diagnosis."`

### Step 10: Assemble Alert Payload
- `triggered = True` only if `tier >= 1` AND `consecutive_anomalous_readings >= tier_minimum`.
- `sos_available = True` only if `tier >= 4` (status `sos` or `medical_attention`).
- Return full Layer 3 payload.

---

## 🔄 In-Memory State Structure (per user_id)
```python
anomaly_state = {
    "user_id": str,
    "consecutive_anomalous_readings": int,  # resets on any normal reading
    "current_status": str,                  # current tier name
    "status_start_time": str,               # ISO8601, when current tier began
    "last_reading_time": str                # ISO8601
}
```
- Stored in a `dict` keyed by `user_id` in FastAPI app state.
- **Lost on server restart** — acceptable for V1. Baseline and history persist in DB.

---

## ⚠️ Edge Cases & Invariants

| # | Scenario | Handling |
|---|----------|----------|
| 1 | Single extreme spike (> 6 std dev) | Triggers `sos` immediately regardless of consecutive count |
| 2 | Baseline `resting_hr_std == 0` | Floored to `0.1` in baseline engine; no division-by-zero |
| 3 | Activity state = `exercise` with extreme HR | Relaxed multiplier applied; may still trigger if very extreme |
| 4 | Reading arrives out of order | Sort by timestamp in baseline window query; alert engine processes in receive order (V1 simplicity) |
| 5 | User has no baseline yet | Step 1 guard returns early. No alert. |
| 6 | Multiple users on same instance | Each user has independent anomaly counter in `anomaly_state` dict |

---

## 🔒 IMMUTABLE Rules (from gemini.md)
- **NEVER** trigger from a single noisy reading.
- **NEVER** skip activity context when interpreting heart rate.
- **NEVER** use population baselines.
- **NEVER** use the words "heart attack", "diagnosis", "detect disease", or "predict".

---

## 🔄 Change Log
| Date | Change | Reason |
|------|--------|--------|
| 2026-09-17 | SOP created | Phase 3 Architect kick-off |
