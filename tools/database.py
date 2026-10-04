"""
database.py — Heart Guard V1
Layer: Foundation — SQLite persistence via aiosqlite
SOP: architecture/database_sop.md
"""

import aiosqlite
import json
from typing import Optional
from datetime import datetime, timezone

DB_PATH = "heartguard.db"


async def init_db() -> None:
    """Create all tables if they do not exist. Called once at startup."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS raw_readings (
                reading_id          TEXT PRIMARY KEY,
                user_id             TEXT NOT NULL,
                device_id           TEXT NOT NULL,
                timestamp           TEXT NOT NULL,
                heart_rate_bpm      REAL,
                hr_confidence       REAL,
                temperature_celsius REAL,
                activity_magnitude  REAL,
                activity_state      TEXT,
                signal_quality      TEXT,
                created_at          TEXT
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_user_time
            ON raw_readings(user_id, timestamp)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS baselines (
                user_id             TEXT PRIMARY KEY,
                computed_at         TEXT,
                sample_count        INTEGER,
                baseline_established INTEGER,
                resting_hr_mean     REAL,
                resting_hr_std      REAL,
                resting_hr_p5       REAL,
                resting_hr_p95      REAL,
                exercise_hr_mean    REAL,
                exercise_hr_std     REAL,
                temp_mean           REAL,
                temp_std            REAL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                alert_id                TEXT PRIMARY KEY,
                user_id                 TEXT NOT NULL,
                timestamp               TEXT NOT NULL,
                status                  TEXT,
                triggered               INTEGER,
                hr_bpm                  REAL,
                activity_state          TEXT,
                temperature_celsius     REAL,
                hr_deviation_std        REAL,
                severity_score          INTEGER,
                duration_minutes        REAL,
                consecutive_anomalous   INTEGER,
                explanation             TEXT,
                sos_available           INTEGER,
                created_at              TEXT
            )
        """)
        await db.commit()


async def save_reading(reading: dict) -> None:
    """INSERT a Layer 1 processed reading. INSERT OR IGNORE for idempotency."""
    async with aiosqlite.connect(DB_PATH) as db:
        derived = reading.get("derived", {})
        await db.execute(
            """
            INSERT OR IGNORE INTO raw_readings
                (reading_id, user_id, device_id, timestamp,
                 heart_rate_bpm, hr_confidence, temperature_celsius,
                 activity_magnitude, activity_state, signal_quality, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading["reading_id"],
                reading["user_id"],
                reading["device_id"],
                reading["timestamp"],
                derived.get("heart_rate_bpm"),
                derived.get("hr_confidence"),
                derived.get("temperature_celsius"),
                derived.get("activity_magnitude"),
                derived.get("activity_state"),
                reading.get("signal_quality"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db.commit()


async def get_recent_readings(user_id: str, hours: int = 168) -> list[dict]:
    """
    Return readings for a user from the last N hours.
    Used by baseline engine for the 7-day rolling window.
    """
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM raw_readings
            WHERE user_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (user_id, cutoff),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_user_ids() -> list[str]:
    """Return distinct user_ids from raw_readings. Used for startup baseline recomputation."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT user_id FROM raw_readings") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def save_baseline(baseline: dict) -> None:
    """INSERT OR REPLACE baseline for a user (upsert)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO baselines
                (user_id, computed_at, sample_count, baseline_established,
                 resting_hr_mean, resting_hr_std, resting_hr_p5, resting_hr_p95,
                 exercise_hr_mean, exercise_hr_std, temp_mean, temp_std)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                baseline["user_id"],
                baseline["computed_at"],
                baseline["sample_count"],
                1 if baseline["baseline_established"] else 0,
                baseline.get("resting_hr", {}).get("mean"),
                baseline.get("resting_hr", {}).get("std_dev"),
                baseline.get("resting_hr", {}).get("p5"),
                baseline.get("resting_hr", {}).get("p95"),
                baseline.get("exercise_hr", {}).get("mean") if baseline.get("exercise_hr") else None,
                baseline.get("exercise_hr", {}).get("std_dev") if baseline.get("exercise_hr") else None,
                baseline.get("temperature", {}).get("mean") if baseline.get("temperature") else None,
                baseline.get("temperature", {}).get("std_dev") if baseline.get("temperature") else None,
            ),
        )
        await db.commit()


async def get_baseline(user_id: str) -> Optional[dict]:
    """Return the baseline profile dict for a user, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM baselines WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            r = dict(row)
            # Reconstruct nested schema for downstream compatibility
            return {
                "user_id": r["user_id"],
                "computed_at": r["computed_at"],
                "sample_count": r["sample_count"],
                "baseline_established": bool(r["baseline_established"]),
                "resting_hr": {
                    "mean": r["resting_hr_mean"],
                    "std_dev": max(r["resting_hr_std"] or 0.1, 0.1),  # Floor at 0.1
                    "p5": r["resting_hr_p5"],
                    "p95": r["resting_hr_p95"],
                },
                "exercise_hr": {
                    "mean": r["exercise_hr_mean"],
                    "std_dev": r["exercise_hr_std"],
                } if r["exercise_hr_mean"] is not None else None,
                "temperature": {
                    "mean": r["temp_mean"],
                    "std_dev": r["temp_std"],
                } if r["temp_mean"] is not None else None,
            }


async def save_alert(alert: dict) -> None:
    """INSERT a triggered Layer 3 alert into alert history."""
    async with aiosqlite.connect(DB_PATH) as db:
        current_readings = alert.get("current_readings", {})
        baseline_comp = alert.get("baseline_comparison", {})
        pattern = alert.get("pattern", {})
        await db.execute(
            """
            INSERT OR IGNORE INTO alerts
                (alert_id, user_id, timestamp, status, triggered,
                 hr_bpm, activity_state, temperature_celsius,
                 hr_deviation_std, severity_score, duration_minutes,
                 consecutive_anomalous, explanation, sos_available, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert["alert_id"],
                alert["user_id"],
                alert["timestamp"],
                alert["status"],
                1 if alert.get("triggered") else 0,
                current_readings.get("heart_rate_bpm"),
                current_readings.get("activity_state"),
                current_readings.get("temperature_celsius"),
                baseline_comp.get("hr_deviation_std"),
                pattern.get("severity_score"),
                pattern.get("duration_minutes"),
                pattern.get("consecutive_anomalous_readings"),
                alert.get("explanation"),
                1 if alert.get("sos_available") else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db.commit()


async def get_alert_history(user_id: str, limit: int = 50) -> list[dict]:
    """Return last N triggered alerts for a user, newest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM alerts
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
