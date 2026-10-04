# 🔍 findings.md — Research & Discovery Log
> **STATUS:** 🟢 Research Phase 1 Complete
> **Last Updated:** 2026-09-14
> **Project:** Heart Guard V1

---

## 📡 Tech Stack Decisions

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend | FastAPI (Python) | Async, WebSocket native, fast HTTP — ideal for real-time sensor ingestion |
| Database | SQLite | Zero-config, file-based, sufficient for V1 prototype |
| ORM | SQLAlchemy + aiosqlite | Async-safe, avoids thread-lock issues with SQLite |
| Frontend | HTML/CSS/JS | No build step, direct serving from FastAPI |
| Charts | Chart.js | Lightweight, time-series capable, well-documented |
| Signal Processing | HeartPy + SciPy | HeartPy purpose-built for noisy wearable PPG; SciPy for Butterworth filters |

---

## 📚 Key Library Findings

### PPG Signal Processing
- **HeartPy**: Best library for noisy PPG from wearables. Built-in rolling mean, Hampel filter, adaptive peak detection.
- **SciPy `signal.filtfilt`**: Zero-phase Butterworth bandpass (0.5–12 Hz) is the standard for PPG baseline wander removal.
- **Bandpass range**: 0.5 Hz low-cut removes DC baseline wander; 12 Hz high-cut eliminates high-frequency noise.

### Activity Detection (Accelerometer)
- V1 approach: **Rule-based, NOT ML** (deterministic, no training data needed).
- Activity magnitude = sqrt(x² + y² + z²) — subtract gravity component (1g = ~9.8).
- Thresholds:
  - `resting`: magnitude_variance < 0.05 over 10s window
  - `light_activity`: 0.05 ≤ magnitude_variance < 0.3
  - `exercise`: magnitude_variance ≥ 0.3
- This classification gates heart rate alerting.

### Baseline Algorithm
- Rolling window: 7-day sliding window of resting readings.
- Minimum 100 clean resting-state readings to "establish" baseline.
- Stats stored: mean, std_dev, 5th/95th percentile.
- Baseline recomputed every 24 hours (background task).
- Baseline deviation measured in standard deviations (z-score), NOT absolute values — personal relative comparison.

### Alert Engine
- Tier escalation requires BOTH threshold breach AND duration.
- Consecutive anomaly counter resets if a normal reading appears.
- Single noisy reading (low confidence score) is discarded before entering the counter.
- Activity adjustment: if `activity_state = exercise`, the HR threshold multiplier is relaxed (expected elevation).

### WebSocket Architecture
- Hardware → POST `/api/v1/ingest` (HTTP or WebSocket) → backend processes → WebSocket broadcast to dashboard.
- In-memory asyncio.Queue buffers high-frequency readings; batch SQLite writes every 500ms.
- Dashboard connects via WebSocket to `/ws/dashboard` for live push updates.

---

## ⚠️ Known Constraints & Gotchas

| # | Constraint | Mitigation |
|---|-----------|------------|
| 1 | SQLite is NOT thread-safe by default | Use `aiosqlite` for async access + `check_same_thread=False` |
| 2 | PPG baseline wander increases with movement | Apply high-pass filter BEFORE peak detection |
| 3 | Heart rate from PPG is an ESTIMATE | Flag with `hr_confidence` score; discard if < 0.6 |
| 4 | Baseline requires warm-up period | Show "Calibrating..." state on dashboard until 100 readings |
| 5 | Single spike ≠ alert | Minimum 3 consecutive anomalous windows required |
| 6 | Exercise HR is naturally elevated | Accelerometer gating is MANDATORY before HR alert |

---

## 💡 GitHub Reference Repos
- **HeartPy**: https://python-heart-rate-analysis-toolkit.readthedocs.io/
- **Nightbeat** (sleep HR from wrist): https://github.com/eth-siplab/Nightbeat
- **HeartBEAT** (motion artifact removal): https://github.com/olivesgatech/HeartBEAT
- **pybaselines**: https://github.com/derb12/pybaselines
