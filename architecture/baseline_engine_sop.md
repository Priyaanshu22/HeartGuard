# 📊 SOP: Baseline Engine
> **Layer:** 1 → 2 — Processed Readings → Personal Baseline Profile
> **Tool:** `tools/baseline_engine.py`
> **Last Updated:** 2026-09-17
> **Status:** ✅ Active

---

## 🎯 Goal
Compute and persist a **personal baseline profile** (Layer 2) for each user from their recent clean resting readings. This baseline is the ground truth for all alert comparisons — it represents *this person's normal*.

---

## 📥 Input
- **Source:** `raw_readings` table (queried from DB)
- **Filter:** Last 7 days (`168 hours`) of readings WHERE:
  - `activity_state = "resting"`
  - `signal_quality IN ("good", "fair")`
  - `heart_rate_bpm IS NOT NULL`
  - `hr_confidence >= 0.6`

---

## 📤 Output
Updated row in `baselines` table (Layer 2 schema per `gemini.md`).

---

## ⚙️ Computation Pipeline

### Step 1: Data Pull
- Call `database.get_recent_readings(user_id, hours=168)`.
- Filter locally for the clean resting subset defined above.

### Step 2: Sufficiency Check
- Count filtered readings. Store as `sample_count`.
- If `sample_count < 100`:
  - Set `baseline_established = False`.
  - Still upsert to DB to record current state and sample count.
  - **Return early.** The alert engine will check `baseline_established` before comparing.
  - Dashboard should show "🔄 Calibrating… (X/100 readings)" in this state.

### Step 3: Heart Rate Statistics
- Extract all `heart_rate_bpm` values into a list.
- Compute:
  - `resting_hr_mean = mean(hr_values)`
  - `resting_hr_std = std(hr_values)` — population std (ddof=0 for V1 simplicity)
  - `resting_hr_p5 = percentile(hr_values, 5)`
  - `resting_hr_p95 = percentile(hr_values, 95)`
- Use `numpy` or `statistics` module.

### Step 4: Exercise HR (Optional — only if sufficient data)
- Separately filter readings WHERE `activity_state IN ("light_activity", "exercise")`.
- If count >= 20:
  - Compute `exercise_hr_mean` and `exercise_hr_std`.
- Else: store `null` for both.

### Step 5: Temperature Statistics
- Extract all `temperature_celsius` values (exclude nulls).
- Compute:
  - `temp_mean = mean(temp_values)`
  - `temp_std = std(temp_values)`
- If fewer than 20 valid temperature readings: store `null`.

### Step 6: Upsert to Database
- Assemble Layer 2 payload.
- Call `database.save_baseline(baseline)`.
- This is an INSERT OR REPLACE — always overwrites the previous baseline for the user.

---

## 🔁 Trigger Schedule
- **On startup:** Run once for all known users.
- **Recurring:** Every **24 hours** via FastAPI `BackgroundTasks` or `asyncio` scheduled task.
- **On demand:** Can be triggered via admin endpoint `POST /api/v1/admin/recompute_baseline/{user_id}`.

---

## ⚠️ Edge Cases & Invariants

| # | Scenario | Handling |
|---|----------|----------|
| 1 | Fewer than 100 clean resting readings | `baseline_established = False`; alert engine returns early |
| 2 | User only has exercise data | Resting baseline unavailable; `baseline_established = False` |
| 3 | Standard deviation is 0 (identical readings — impossible but guard) | Floor `resting_hr_std` at `0.1` to prevent division-by-zero in alert engine |
| 4 | No temperature data | `temp_mean = null`, temperature alerts disabled |
| 5 | User's data gap > 7 days | Sample count will drop; baseline may de-establish. Expected behavior. |

---

## 🔒 Invariant
> **NEVER** compare a user's reading against population averages. The baseline profile is *exclusively* derived from that user's own historical data.

---

## 🔄 Change Log
| Date | Change | Reason |
|------|--------|--------|
| 2026-09-17 | SOP created | Phase 3 Architect kick-off |
