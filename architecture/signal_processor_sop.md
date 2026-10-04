# 🔬 SOP: Signal Processor
> **Layer:** 1 — Raw Sensor → Processed Reading
> **Tool:** `tools/signal_processor.py`
> **Last Updated:** 2026-09-17
> **Status:** ✅ Active

---

## 🎯 Goal
Transform a raw **Layer 0** sensor payload from the microcontroller into a validated, enriched **Layer 1** processed reading ready for baseline comparison and storage.

---

## 📥 Input
**Source:** HTTP POST to `/api/v1/ingest` or WebSocket message
**Schema:** Layer 0 Raw Sensor Payload (see `gemini.md`)

```json
{
  "device_id": "string",
  "user_id": "string",
  "timestamp": "ISO8601",
  "sensor": {
    "ppg": { "raw_signal": [0.0], "sampling_rate_hz": 100 },
    "accelerometer": { "x": 0.0, "y": 0.0, "z": 0.0 },
    "temperature": { "value_celsius": 0.0 }
  }
}
```

---

## 📤 Output
**Schema:** Layer 1 Processed Reading (see `gemini.md`)

```json
{
  "reading_id": "uuid",
  "user_id": "string",
  "device_id": "string",
  "timestamp": "ISO8601",
  "derived": {
    "heart_rate_bpm": 72.0,
    "hr_confidence": 0.85,
    "temperature_celsius": 36.8,
    "activity_magnitude": 0.12,
    "activity_state": "resting"
  },
  "signal_quality": "good"
}
```

---

## ⚙️ Processing Pipeline (Ordered Steps)

### Step 1: Input Validation
- Reject payload if `raw_signal` is empty or has fewer than 50 samples.
- Reject payload if `timestamp` cannot be parsed as ISO8601.
- Return `signal_quality: "rejected"` immediately if validation fails. Do NOT proceed.

### Step 2: PPG Signal Filtering
- Apply a **zero-phase Butterworth bandpass filter** using `scipy.signal.filtfilt`.
  - Low cutoff: `0.5 Hz` (removes DC baseline wander)
  - High cutoff: `12.0 Hz` (removes high-frequency noise)
  - Filter order: 4
- This MUST be applied before any peak detection.

### Step 3: Signal Quality Assessment
- Use `heartpy.process()` to attempt heart rate extraction.
- Check `heartpy` output for `bpm` and its confidence proxy (ratio of valid beats).
- Assign `signal_quality`:
  - `"good"`: `hr_confidence >= 0.8`
  - `"fair"`: `0.6 <= hr_confidence < 0.8`
  - `"poor"`: `hr_confidence < 0.6` → flag but still pass through; alert engine will discard it.
- **DO NOT discard the reading here.** Pass `signal_quality` downstream; the alert engine decides.

### Step 4: Heart Rate Extraction
- Extract `heart_rate_bpm` from `heartpy` working data.
- Round to 1 decimal place.
- If HeartPy fails to produce a valid BPM (exception), set:
  - `heart_rate_bpm: null`
  - `hr_confidence: 0.0`
  - `signal_quality: "failed"`

### Step 5: Accelerometer — Activity State Classification
- Compute `activity_magnitude` = `sqrt(x² + y² + z²)`
- Subtract gravity component: `activity_net = abs(activity_magnitude - 9.8)` (approximate for prototype)
- **Activity State Rules (deterministic):**
  | State | Rule |
  |-------|------|
  | `resting` | `activity_net < 0.5` |
  | `light_activity` | `0.5 <= activity_net < 2.0` |
  | `exercise` | `activity_net >= 2.0` |
- Store `activity_magnitude` (raw) and `activity_state` (classified).

### Step 6: Temperature Pass-Through
- Read `sensor.temperature.value_celsius` directly.
- Store as `temperature_celsius`. No filtering needed for V1.
- Sanity check: reject if outside `[30.0, 42.0]` range (physical impossibility). Set to `null` if rejected.

### Step 7: Assemble Output
- Generate a new `reading_id` using `uuid.uuid4()`.
- Assemble and return the Layer 1 JSON object.

---

## ⚠️ Edge Cases & Known Gotchas

| # | Scenario | Handling |
|---|----------|----------|
| 1 | PPG array has < 50 samples | Reject immediately, `signal_quality: "rejected"` |
| 2 | HeartPy throws exception (too noisy) | `hr_confidence: 0.0`, `signal_quality: "failed"` |
| 3 | Accelerometer reads exactly 0,0,0 (hardware fault) | `activity_state: "unknown"`, flag in output |
| 4 | Temperature out of physiological range | `temperature_celsius: null` |
| 5 | Duplicate `device_id` + `timestamp` within 1s | Database layer deduplication (not this tool's concern) |

---

## 🔄 Change Log
| Date | Change | Reason |
|------|--------|--------|
| 2026-09-17 | SOP created | Phase 3 Architect kick-off |
