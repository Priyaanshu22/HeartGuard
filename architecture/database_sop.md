# 🗄️ SOP: Database
> **Layer:** Foundation — Persistent Storage
> **Tool:** `tools/database.py`
> **Last Updated:** 2026-09-17
> **Status:** ✅ Active

---

## 🎯 Goal
Define and manage the SQLite database schema, async ORM models, and all CRUD operations used by Heart Guard V1.

---

## 🏛️ Database: `heartguard.db` (SQLite)

Stored at project root. **Never stored in `.tmp/`** (it is persistent, not ephemeral).

---

## 📋 Table Definitions

### Table: `raw_readings` (Layer 1 Archive)
Stores all processed Layer 1 readings from the signal processor.

| Column | Type | Notes |
|--------|------|-------|
| `reading_id` | TEXT PRIMARY KEY | UUID |
| `user_id` | TEXT NOT NULL | Foreign key (logical) |
| `device_id` | TEXT NOT NULL | |
| `timestamp` | TEXT NOT NULL | ISO8601 string |
| `heart_rate_bpm` | REAL | nullable |
| `hr_confidence` | REAL | 0.0–1.0 |
| `temperature_celsius` | REAL | nullable |
| `activity_magnitude` | REAL | |
| `activity_state` | TEXT | resting/light_activity/exercise/unknown |
| `signal_quality` | TEXT | good/fair/poor/failed/rejected |
| `created_at` | TEXT | Server time, ISO8601 |

**Index:** `(user_id, timestamp)` for baseline window queries.

---

### Table: `baselines` (Layer 2 Profiles)
One row per user. Upserted (replaced) on each recomputation.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | TEXT PRIMARY KEY | |
| `computed_at` | TEXT | ISO8601 |
| `sample_count` | INTEGER | Clean resting readings used |
| `baseline_established` | INTEGER | 0 or 1 (SQLite boolean) |
| `resting_hr_mean` | REAL | |
| `resting_hr_std` | REAL | |
| `resting_hr_p5` | REAL | 5th percentile |
| `resting_hr_p95` | REAL | 95th percentile |
| `exercise_hr_mean` | REAL | nullable until sufficient exercise data |
| `exercise_hr_std` | REAL | nullable |
| `temp_mean` | REAL | |
| `temp_std` | REAL | |

---

### Table: `alerts` (Layer 3 History)
All triggered alerts. Never deleted. Append-only.

| Column | Type | Notes |
|--------|------|-------|
| `alert_id` | TEXT PRIMARY KEY | UUID |
| `user_id` | TEXT NOT NULL | |
| `timestamp` | TEXT NOT NULL | ISO8601 |
| `status` | TEXT | Tier name (e.g., `worth_watching`) |
| `triggered` | INTEGER | Always 1 for stored alerts |
| `hr_bpm` | REAL | Current reading at trigger time |
| `activity_state` | TEXT | At trigger time |
| `temperature_celsius` | REAL | At trigger time |
| `hr_deviation_std` | REAL | Z-score at trigger |
| `severity_score` | INTEGER | 1–4 |
| `duration_minutes` | REAL | |
| `consecutive_anomalous` | INTEGER | |
| `explanation` | TEXT | Plain English description |
| `sos_available` | INTEGER | 0 or 1 |
| `created_at` | TEXT | |

---

## ⚙️ CRUD Operations

### `init_db()`
- Create all tables if they don't exist (`CREATE TABLE IF NOT EXISTS`).
- Called once at FastAPI startup.

### `save_reading(reading: dict) → None`
- INSERT into `raw_readings`.
- Use `INSERT OR IGNORE` to handle duplicate `reading_id` gracefully.

### `get_recent_readings(user_id: str, hours: int = 168) → List[dict]`
- SELECT from `raw_readings` WHERE `user_id = ?` AND `timestamp >= ?`
- Used by `baseline_engine.py` for the 7-day rolling window.
- Return rows as list of dicts.

### `save_baseline(baseline: dict) → None`
- INSERT OR REPLACE into `baselines`.

### `get_baseline(user_id: str) → dict | None`
- SELECT from `baselines` WHERE `user_id = ?`.
- Return `None` if no baseline exists yet.

### `save_alert(alert: dict) → None`
- INSERT into `alerts`.

### `get_alert_history(user_id: str, limit: int = 50) → List[dict]`
- SELECT from `alerts` WHERE `user_id = ?` ORDER BY `timestamp DESC` LIMIT ?

---

## ⚠️ SQLite Safety Rules
1. **Always use `aiosqlite`** for async access — never `sqlite3` directly in async context.
2. Use parameterized queries (`?` placeholders). **NEVER** format SQL strings with f-strings (SQL injection risk even in local dev).
3. `check_same_thread=False` is required when sharing connection across async workers.
4. Write operations are serialized through a single async context manager.

---

## 🔄 Change Log
| Date | Change | Reason |
|------|--------|--------|
| 2026-09-17 | SOP created | Phase 3 Architect kick-off |
