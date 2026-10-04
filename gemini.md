# ⚡ gemini.md — Project Constitution
> **STATUS:** 🟢 ACTIVE — Discovery Complete, Awaiting Blueprint Approval
> **Last Updated:** 2026-09-14
> **Project:** Heart Guard V1

---

## 🧭 North Star
> **Detect meaningful changes from a person's personal health baseline and provide an understandable early-warning status with appropriate alerts.**
> The system does NOT diagnose disease or predict events. It detects unusual *patterns* early.

---

## 📐 Data Schema

### Layer 0: Raw Sensor Payload (Microcontroller → Backend)
```json
{
  "device_id": "string",
  "user_id": "string",
  "timestamp": "ISO8601",
  "sensor": {
    "ppg": {
      "raw_signal": [0.0],
      "sampling_rate_hz": 100
    },
    "accelerometer": {
      "x": 0.0,
      "y": 0.0,
      "z": 0.0
    },
    "temperature": {
      "value_celsius": 0.0
    }
  }
}
```

### Layer 1: Processed Reading (After signal_processor.py)
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

### Layer 2: Baseline Profile (Stored in DB per user)
```json
{
  "user_id": "string",
  "computed_at": "ISO8601",
  "sample_count": 500,
  "baseline_established": true,
  "resting_hr": {
    "mean": 68.0,
    "std_dev": 5.2,
    "p5": 58.0,
    "p95": 78.0
  },
  "exercise_hr": {
    "mean": 130.0,
    "std_dev": 12.0
  },
  "temperature": {
    "mean": 36.7,
    "std_dev": 0.3
  }
}
```

### Layer 3: Alert Payload (Output — Dashboard & Storage)
```json
{
  "alert_id": "uuid",
  "user_id": "string",
  "timestamp": "ISO8601",
  "status": "worth_watching",
  "triggered": true,
  "current_readings": {
    "heart_rate_bpm": 112.0,
    "activity_state": "resting",
    "temperature_celsius": 37.4
  },
  "baseline_comparison": {
    "hr_deviation_std": 8.46,
    "hr_deviation_percent": 64.7,
    "temp_deviation_celsius": 0.7,
    "activity_adjusted": false
  },
  "pattern": {
    "duration_minutes": 12.0,
    "consecutive_anomalous_readings": 7,
    "severity_score": 3
  },
  "explanation": "Your heart rate has been elevated (112 bpm vs your resting baseline of 68 bpm) for 12 minutes while you appear to be at rest. This is unusual for you.",
  "disclaimer": "This is a personal pattern alert, not a medical diagnosis.",
  "sos_available": true
}
```

---

## 🔌 Integrations & Credentials
| Service | Purpose | Key Status |
|---------|---------|------------|
| Microcontroller (Hardware) | Raw sensor data source | N/A — direct POST/WebSocket |
| SQLite (local) | Persistent storage | No key needed |
| FastAPI (local) | Backend + API | No key needed |

---

## 📦 Source of Truth
**Primary:** Raw sensor data from prototype hardware (PPG, Accelerometer, Temperature).
**Secondary (derived, persistent):** Processed readings and personal baseline stored in SQLite database.

---

## 🚚 Delivery Mechanism
**Web Dashboard (HTML/CSS/JS)** served by the FastAPI backend.
Real-time updates via **WebSocket** to the dashboard.
Dashboard sections:
1. Live Readings Panel
2. 24h Trend Charts
3. Personal Baseline Profile
4. Active Alert Panel (with explanation)
5. Alert History
6. SOS Button (always visible when status >= Medical Attention)

---

## 📏 Behavioral Rules (IMMUTABLE)

### ✅ DO Rules
- Compare readings against the user's **personal baseline**, not population averages.
- Consider `activity_state` from accelerometer before flagging heart rate anomalies.
- Require **minimum 3 consecutive anomalous readings** (smoothing window) before escalating status.
- Require **sustained pattern** (configurable duration threshold per tier) before escalating.
- Explain every alert in plain English with specific numbers.
- Escalate status gradually: `normal` → `worth_noting` → `worth_watching` → `medical_attention` → `sos`.
- Mark all sensor-derived values as **estimates**.

### ❌ DO NOT Rules
- **NEVER** use the words "heart attack", "diagnosis", "detect disease", or "predict".
- **NEVER** trigger an alert from a single noisy reading.
- **NEVER** skip activity context when interpreting heart rate.
- **NEVER** hardcode population baselines as the primary comparison metric.
- **NEVER** store API keys or credentials in code — use `.env`.
- **NEVER** include BP, glucose, microphone, or CPR logic in V1.

---

## 🎚️ Alert Status Tiers

| Status | Tier | HR Deviation | Duration | Action |
|--------|------|-------------|----------|--------|
| Normal | 0 | < 2 std dev | Any | None |
| Worth Noting | 1 | 2–3 std dev | > 5 min | Soft notification |
| Worth Watching | 2 | 3–4 std dev | > 10 min | Dashboard warning |
| Medical Attention | 3 | > 4 std dev | > 15 min | Prominent alert |
| SOS | 4 | > 5 std dev | > 20 min OR extreme spike | SOS button visible |

---

## 🏛️ Architectural Invariants
1. LLMs are probabilistic — all alert logic must be deterministic Python (no AI for decisions).
2. No secrets hardcoded — all credentials live in `.env`.
3. All intermediate/temp data lives in `.tmp/` — ephemeral.
4. A project is only "Complete" when the dashboard is live and receiving real data.
5. If alert logic changes → update `architecture/alert_engine_sop.md` BEFORE updating code.
6. Signal quality must be validated before any baseline comparison.
7. Baseline requires minimum 100 clean readings before it is considered "established".

---

## 🔄 Schema Change Log
| Date | Change | Reason |
|------|--------|--------|
| 2026-09-14 | Full schema defined | Discovery Questions answered |
| 2026-09-14 | Alert tier table added | Q5 behavioral rules |

---

## 🛠️ Maintenance Log
| Date | Event | Resolution |
|------|-------|------------|
| 2026-09-14 | Constitution initialized | Protocol 0 complete |
