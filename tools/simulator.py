"""
simulator.py — Heart Guard V1
Purpose: Generate synthetic sensor data for testing the full pipeline.
This is a development/testing tool — NOT part of production.
Run: python tools/simulator.py
"""

import json
import math
import random
import time
import argparse
import asyncio
import uuid
from datetime import datetime, timezone

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# ─── Signal Generation ────────────────────────────────────────────────────────

def generate_ppg_signal(
    heart_rate_bpm: float = 72.0,
    sampling_rate: int = 100,
    duration_seconds: float = 5.0,
    noise_level: float = 0.05,
) -> list[float]:
    """
    Synthesize a PPG-like signal at a given heart rate.
    Uses a sum of sinusoids to approximate pulse waveform morphology.
    Not physiologically accurate — purely for pipeline testing.
    """
    n_samples = int(sampling_rate * duration_seconds)
    freq = heart_rate_bpm / 60.0  # BPM → Hz
    t = [i / sampling_rate for i in range(n_samples)]

    signal = []
    for ti in t:
        # Fundamental + harmonics (crude pulse shape approximation)
        val = (
            math.sin(2 * math.pi * freq * ti)
            + 0.5 * math.sin(2 * math.pi * 2 * freq * ti)
            + 0.2 * math.sin(2 * math.pi * 3 * freq * ti)
            + random.gauss(0, noise_level)
        )
        if noise_level > 1.0 and random.random() < 0.25:
            val += random.choice([-15.0, 15.0])  # large motion artifact spike
        signal.append(round(val, 6))

    return signal


def generate_payload(
    user_id: str = "test_user_001",
    device_id: str = "device_001",
    heart_rate_bpm: float = 72.0,
    activity_state: str = "resting",
    temperature: float = 36.7,
    noise_level: float = 0.05,
    sampling_rate: int = 100,
) -> dict:
    """
    Build a full Layer 0 raw sensor payload for a given scenario.
    """
    # Accelerometer values by activity state
    accel_map = {
        "resting":        {"x": 0.1,  "y": 9.7,  "z": 0.2},   # activity_net < 0.5
        "light_activity": {"x": 0.8,  "y": 9.8,  "z": 1.1},   # 0.5 ≤ net < 2.0
        "exercise":       {"x": 3.5,  "y": 10.5, "z": 4.2},   # net ≥ 2.0
    }
    accel = accel_map.get(activity_state, accel_map["resting"])

    # Add small jitter to make it realistic
    accel = {k: round(v + random.gauss(0, 0.1), 4) for k, v in accel.items()}

    return {
        "device_id": device_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sensor": {
            "ppg": {
                "raw_signal": generate_ppg_signal(
                    heart_rate_bpm=heart_rate_bpm,
                    sampling_rate=sampling_rate,
                    noise_level=noise_level,
                ),
                "sampling_rate_hz": sampling_rate,
            },
            "accelerometer": accel,
            "temperature": {
                "value_celsius": round(temperature + random.gauss(0, 0.05), 2)
            },
        },
    }


# ─── Scenario Presets ────────────────────────────────────────────────────────

SCENARIOS = {
    "normal_resting": {
        "description": "Normal resting heart rate, good signal",
        "heart_rate_bpm": 68.0,
        "activity_state": "resting",
        "temperature": 36.7,
        "noise_level": 0.03,
    },
    "elevated_resting": {
        "description": "Elevated HR while resting — should trigger alerts over time",
        "heart_rate_bpm": 112.0,
        "activity_state": "resting",
        "temperature": 37.4,
        "noise_level": 0.05,
    },
    "exercise_normal": {
        "description": "High HR during exercise — should NOT trigger (activity gating)",
        "heart_rate_bpm": 130.0,
        "activity_state": "exercise",
        "temperature": 36.9,
        "noise_level": 0.07,
    },
    "noisy_signal": {
        "description": "Very noisy signal — should produce poor/failed quality",
        "heart_rate_bpm": 70.0,
        "activity_state": "resting",
        "temperature": 36.6,
        "noise_level": 5.0,
    },
    "extreme_spike": {
        "description": "Extreme HR spike > 6 std dev — should trigger SOS immediately",
        "heart_rate_bpm": 180.0,
        "activity_state": "resting",
        "temperature": 37.8,
        "noise_level": 0.03,
    },
}


# ─── CLI Modes ────────────────────────────────────────────────────────────────

async def send_to_api(payload: dict, base_url: str) -> None:
    """POST a payload to the local FastAPI server."""
    if not HTTPX_AVAILABLE:
        print("[simulator] httpx not installed. Run: pip install httpx")
        return
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{base_url}/api/v1/ingest", json=payload, timeout=5.0)
            print(f"  → [{resp.status_code}] {resp.text[:200]}")
        except httpx.ConnectError:
            print(f"  → [ERROR] Cannot connect to {base_url}. Is the server running?")


def run_local_test(scenario_name: str, user_id: str) -> None:
    """
    Run a local dry test (no HTTP) — prints the generated payload JSON.
    Used to validate payload generation without a running server.
    """
    scenario = SCENARIOS.get(scenario_name)
    if not scenario:
        print(f"[simulator] Unknown scenario: {scenario_name}. Available: {list(SCENARIOS.keys())}")
        return

    print(f"\n{'='*60}")
    print(f"  SCENARIO: {scenario_name}")
    print(f"  {scenario['description']}")
    print(f"{'='*60}")
    payload = generate_payload(user_id=user_id, **{k: v for k, v in scenario.items() if k != "description"})
    print(json.dumps(payload, indent=2)[:2000])
    print(f"\n[simulator] Payload generated. {len(payload['sensor']['ppg']['raw_signal'])} PPG samples.")


async def run_continuous(
    scenario_name: str,
    user_id: str,
    base_url: str,
    count: int,
    interval_seconds: float,
) -> None:
    """Continuously send readings to the API — simulates a live device stream."""
    scenario = SCENARIOS.get(scenario_name)
    if not scenario:
        print(f"[simulator] Unknown scenario: {scenario_name}")
        return

    print(f"\n[simulator] Starting continuous feed: {scenario_name} → {base_url}")
    print(f"  Readings: {count} | Interval: {interval_seconds}s")
    print(f"  {scenario['description']}\n")

    kwargs = {k: v for k, v in scenario.items() if k != "description"}
    for i in range(count):
        payload = generate_payload(user_id=user_id, **kwargs)
        print(f"  [{i+1}/{count}] Sending {scenario_name} reading...", end="")
        await send_to_api(payload, base_url)
        if i < count - 1:
            await asyncio.sleep(interval_seconds)

    print(f"\n[simulator] Done. Sent {count} readings.")


# ─── Build Baseline Dataset ───────────────────────────────────────────────────

async def seed_baseline(user_id: str, base_url: str, n: int = 120) -> None:
    """
    Send N normal resting readings to establish a baseline.
    Call this before testing alert scenarios.
    """
    print(f"\n[simulator] Seeding baseline for {user_id} with {n} normal resting readings...")
    for i in range(n):
        payload = generate_payload(
            user_id=user_id,
            heart_rate_bpm=random.gauss(68.0, 5.0),  # Natural variation
            activity_state="resting",
            temperature=random.gauss(36.7, 0.2),
            noise_level=0.04,
        )
        print(f"  [{i+1}/{n}] Seeding...", end="")
        await send_to_api(payload, base_url)
        await asyncio.sleep(0.1)  # Fast for seeding

    print(f"\n[simulator] Baseline seeded. Triggering recompute...")
    if HTTPX_AVAILABLE:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/api/v1/admin/recompute_baseline/{user_id}", timeout=10.0
            )
            print(f"  → Recompute: [{resp.status_code}] {resp.text[:200]}")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Heart Guard Sensor Simulator")
    parser.add_argument("--mode", choices=["local", "send", "continuous", "seed"],
                        default="local", help="Execution mode")
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()),
                        default="normal_resting", help="Scenario preset")
    parser.add_argument("--user", default="test_user_001", help="User ID")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--count", type=int, default=15, help="Number of readings (continuous/seed mode)")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between readings (continuous mode)")

    args = parser.parse_args()

    if args.mode == "local":
        run_local_test(args.scenario, args.user)
    elif args.mode == "send":
        payload = generate_payload(user_id=args.user, **{k: v for k, v in SCENARIOS[args.scenario].items() if k != "description"})
        asyncio.run(send_to_api(payload, args.url))
    elif args.mode == "continuous":
        asyncio.run(run_continuous(args.scenario, args.user, args.url, args.count, args.interval))
    elif args.mode == "seed":
        asyncio.run(seed_baseline(args.user, args.url, args.count))
