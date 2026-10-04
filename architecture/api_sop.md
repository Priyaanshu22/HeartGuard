# 🌐 SOP: API & WebSocket
> **Layer:** Integration — FastAPI Routes + WebSocket Broadcast
> **Tool:** `tools/main.py`
> **Last Updated:** 2026-09-17
> **Status:** ✅ Active

---

## 🎯 Goal
Define all HTTP endpoints and WebSocket connections for Heart Guard V1. The API is the nervous system — it receives data from hardware, triggers the processing pipeline, and broadcasts results to the dashboard in real-time.

---

## 🏛️ Application Structure

```
FastAPI App
├── Startup: init_db(), schedule baseline recomputation
├── Static files: /static/ → serves dashboard HTML/CSS/JS
├── HTTP Routes:
│   ├── POST /api/v1/ingest          (hardware → backend)
│   ├── GET  /api/v1/status/{user_id}
│   ├── GET  /api/v1/history/{user_id}
│   ├── GET  /api/v1/baseline/{user_id}
│   └── POST /api/v1/admin/recompute_baseline/{user_id}
└── WebSocket:
    └── /ws/dashboard/{user_id}     (backend → dashboard)
```

---

## 📡 Endpoints

### `POST /api/v1/ingest`
**Purpose:** Receive raw sensor payload from microcontroller.
**Request Body:** Layer 0 Raw Sensor Payload JSON.
**Pipeline (must be called in order):**
1. `signal_processor.process(payload)` → Layer 1 reading
2. `database.save_reading(reading)` → persist
3. `baseline = database.get_baseline(user_id)` → fetch baseline
4. `alert = alert_engine.evaluate(reading, baseline, anomaly_state[user_id])` → Layer 3
5. `anomaly_state[user_id]` ← update with new state from alert engine
6. If `alert.triggered`: `database.save_alert(alert)` → persist alert
7. `websocket_manager.broadcast(user_id, alert)` → push to dashboard
**Response:** `{"status": "ok", "reading_id": "uuid", "alert_status": "normal"}`
**Error:** 422 if payload validation fails; 500 with logged error if processing fails.

---

### `GET /api/v1/status/{user_id}`
**Purpose:** Current alert state for a user (for dashboard polling fallback).
**Response:** Latest Layer 3 alert payload from `anomaly_state`.

---

### `GET /api/v1/history/{user_id}?limit=50`
**Purpose:** Last N alerts for the history panel.
**Response:** `{"alerts": [alert_payload, ...]}`

---

### `GET /api/v1/baseline/{user_id}`
**Purpose:** Return current baseline profile for dashboard display.
**Response:** Layer 2 baseline JSON + `calibrating: true/false`.

---

### `POST /api/v1/admin/recompute_baseline/{user_id}`
**Purpose:** Force baseline recomputation (for testing/admin use).
**No auth in V1** (local only — add token in V2).
**Response:** `{"status": "ok", "baseline_established": true, "sample_count": 347}`

---

### `WebSocket /ws/dashboard/{user_id}`
**Purpose:** Real-time push of alert payloads to dashboard.

**Connection Lifecycle:**
1. Client connects to `/ws/dashboard/{user_id}`.
2. Server registers client in `WebSocketManager`.
3. On each `POST /api/v1/ingest`, server calls `manager.broadcast(user_id, alert_json)`.
4. Dashboard receives JSON and updates UI without polling.
5. On disconnect: remove from `WebSocketManager`. No crash if broadcast to disconnected client.

**WebSocket Message Format:**
```json
{
  "type": "alert_update",
  "payload": { ...Layer 3 Alert Payload... }
}
```

**WebSocketManager Class:**
```python
class WebSocketManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket): ...
    async def disconnect(self, user_id: str, ws: WebSocket): ...
    async def broadcast(self, user_id: str, message: dict): ...
```
- A user can have multiple dashboard tabs open. All receive the broadcast.

---

## 🚀 Startup Tasks (on `@app.on_event("startup")`)
1. Call `await database.init_db()` — create tables if not exist.
2. Initialize `anomaly_state = {}` in app state.
3. Recompute baselines for all known users (async background task).
4. Schedule baseline recomputation every 24 hours.

---

## 📁 Static File Serving
- Mount `/static` to serve `static/` directory (CSS, JS, assets).
- Serve `static/index.html` at root `/`.
- FastAPI `StaticFiles` mount: `app.mount("/static", StaticFiles(directory="static"), name="static")`

---

## ⚠️ Error Handling
- All route handlers wrapped in try/except.
- Errors logged to console with timestamp and `user_id`.
- HTTP 500 returned on unexpected errors — never let unhandled exceptions crash the server.
- WebSocket broadcast errors: catch and log, remove dead connection, continue.

---

## 🔄 Change Log
| Date | Change | Reason |
|------|--------|--------|
| 2026-09-17 | SOP created | Phase 3 Architect kick-off |
