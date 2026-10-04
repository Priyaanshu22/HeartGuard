"""
main.py — Heart Guard V1
FastAPI application entry point.
Layer: Integration — HTTP + WebSocket server
SOP: architecture/api_sop.md
"""

import asyncio
import json
import sys
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

# Ensure tools/ is importable when running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from tools import database, signal_processor, alert_engine, baseline_engine


# ─── WebSocket Manager ────────────────────────────────────────────────────────

class WebSocketManager:
    """Manages WebSocket connections per user. Supports multiple tabs per user."""

    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.setdefault(user_id, []).append(ws)
        print(f"[ws] {user_id} connected. Total connections: {len(self.connections[user_id])}")

    def disconnect(self, user_id: str, ws: WebSocket) -> None:
        if user_id in self.connections:
            self.connections[user_id] = [c for c in self.connections[user_id] if c != ws]
            if not self.connections[user_id]:
                del self.connections[user_id]
        print(f"[ws] {user_id} disconnected.")

    async def broadcast(self, user_id: str, message: dict) -> None:
        if user_id not in self.connections:
            return
        dead = []
        for ws in self.connections[user_id]:
            try:
                await ws.send_json({"type": "alert_update", "payload": message})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)


ws_manager = WebSocketManager()


# ─── Application State (in-memory) ───────────────────────────────────────────
# anomaly_state: keyed by user_id — tracks consecutive anomalous readings.
# Lost on restart; acceptable for V1. History persists in DB.

anomaly_state: dict[str, dict] = {}

def _default_anomaly_state() -> dict:
    return {
        "consecutive_anomalous_readings": 0,
        "current_status": "normal",
        "status_start_time": datetime.now(timezone.utc).isoformat(),
        "last_reading_time": None,
    }


# ─── Startup / Shutdown ───────────────────────────────────────────────────────

async def _schedule_baseline_recompute():
    """Recompute all baselines every 24 hours in the background."""
    while True:
        await asyncio.sleep(86400)  # 24 hours
        print("[scheduler] Running 24h baseline recompute...")
        await baseline_engine.recompute_all()
        print("[scheduler] Baseline recompute complete.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[startup] Initializing Heart Guard V1...")
    await database.init_db()
    print("[startup] Database initialized.")
    await baseline_engine.recompute_all()
    print("[startup] Baselines computed.")
    asyncio.create_task(_schedule_baseline_recompute())
    print("[startup] ✅ Heart Guard V1 is ready.")
    yield
    # Shutdown (nothing to clean up in V1)
    print("[shutdown] Heart Guard shutting down.")


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Heart Guard V1",
    description="Personal cardiac pattern monitoring system",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve static files (dashboard) — created in Phase 4 Stylize
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─── HTTP Routes ──────────────────────────────────────────────────────────────

@app.get("/")
async def serve_dashboard():
    """Serve the dashboard HTML."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(
        {"message": "Heart Guard V1 API is running. Dashboard not yet built (Phase 4)."},
        status_code=200,
    )


@app.post("/api/v1/ingest")
async def ingest(payload: dict):
    """
    Receive raw sensor payload from hardware.
    Pipeline: signal_processor → DB → alert_engine → DB (if alert) → WebSocket broadcast.
    SOP: architecture/api_sop.md
    """
    try:
        # 1. Process raw signal → Layer 1 reading
        reading = signal_processor.process(payload)
        user_id = reading["user_id"]

        # 2. Persist reading
        await database.save_reading(reading)

        # 3. Fetch baseline
        baseline = await database.get_baseline(user_id)

        # 4. Evaluate alert (stateful)
        state = anomaly_state.setdefault(user_id, _default_anomaly_state())
        alert, updated_state = alert_engine.evaluate(reading, baseline, state)
        anomaly_state[user_id] = updated_state

        # 5. Persist if triggered
        if alert.get("triggered"):
            await database.save_alert(alert)

        # 6. Broadcast to dashboard
        await ws_manager.broadcast(user_id, alert)

        return {
            "status": "ok",
            "reading_id": reading["reading_id"],
            "signal_quality": reading["signal_quality"],
            "alert_status": alert["status"],
            "triggered": alert["triggered"],
        }

    except Exception as e:
        print(f"[ingest] ERROR for user {payload.get('user_id', '?')}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/status/{user_id}")
async def get_status(user_id: str):
    """Return current anomaly state for a user (dashboard polling fallback)."""
    state = anomaly_state.get(user_id, _default_anomaly_state())
    baseline = await database.get_baseline(user_id)
    return {
        "user_id": user_id,
        "current_status": state["current_status"],
        "consecutive_anomalous_readings": state["consecutive_anomalous_readings"],
        "baseline_established": baseline["baseline_established"] if baseline else False,
        "sample_count": baseline["sample_count"] if baseline else 0,
        "last_reading_time": state["last_reading_time"],
    }


@app.get("/api/v1/history/{user_id}")
async def get_history(user_id: str, limit: int = 50):
    """Return alert history for dashboard history panel."""
    alerts = await database.get_alert_history(user_id, limit=limit)
    return {"user_id": user_id, "alerts": alerts}


@app.get("/api/v1/baseline/{user_id}")
async def get_baseline_route(user_id: str):
    """Return current baseline profile for dashboard display."""
    baseline = await database.get_baseline(user_id)
    if baseline is None:
        return {
            "user_id": user_id,
            "baseline_established": False,
            "calibrating": True,
            "sample_count": 0,
        }
    return {**baseline, "calibrating": not baseline["baseline_established"]}


@app.post("/api/v1/admin/recompute_baseline/{user_id}")
async def admin_recompute_baseline(user_id: str):
    """Force baseline recomputation for a user. Admin / testing use only."""
    try:
        baseline = await baseline_engine.compute_baseline(user_id)
        return {
            "status": "ok",
            "baseline_established": baseline["baseline_established"],
            "sample_count": baseline["sample_count"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/dashboard/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    Real-time push channel. Dashboard connects here to receive alert updates.
    SOP: architecture/api_sop.md — WebSocket section.
    """
    await ws_manager.connect(user_id, websocket)
    try:
        # Send current state immediately on connect
        baseline = await database.get_baseline(user_id)
        state = anomaly_state.get(user_id, _default_anomaly_state())
        await websocket.send_json({
            "type": "connected",
            "payload": {
                "user_id": user_id,
                "current_status": state["current_status"],
                "baseline_established": baseline["baseline_established"] if baseline else False,
                "sample_count": baseline["sample_count"] if baseline else 0,
            },
        })
        # Keep connection alive; data is pushed from /api/v1/ingest
        while True:
            # Heartbeat ping every 30s to keep connection alive
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
    except Exception as e:
        print(f"[ws] ERROR for {user_id}: {e}")
        ws_manager.disconnect(user_id, websocket)


# ─── Run (dev only) ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tools.main:app", host="0.0.0.0", port=8000, reload=True)
