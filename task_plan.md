# 📋 task_plan.md — Project Task Plan
> **STATUS:** 🟢 ACTIVE — Blueprint Approved, Entering Phase 3: Architect
> **Last Updated:** 2026-09-17
> **Project:** Heart Guard

---

## 🗺️ B.L.A.S.T. Phase Overview

| Phase | Name | Status | Gate |
|-------|------|--------|------|
| 0 | Initialization | ✅ Complete | Files created |
| 1 | Blueprint | ✅ Complete | Discovery Q&A answered, Schema defined |
| 2 | Link | ✅ Complete | Local stack ready |
| 3 | Architect | ✅ Complete | Pipeline validated 100% |
| 4 | Stylize | ✅ Complete | Website & Dashboard built and verified |
| 5 | Trigger | 🟢 ACTIVE | Dev server live at http://localhost:8000 |

---

## ✅ Phase 0 Checklist — Initialization
- [x] Create gemini.md (Project Constitution)
- [x] Create task_plan.md (This file)
- [x] Create findings.md (Research log)
- [x] Create progress.md (Execution log)
- [x] Discovery Questions answered by user
- [x] Data Schema defined in gemini.md
- [x] Blueprint approved

---

## 📦 Phase 1 Checklist — Blueprint
- [x] North Star confirmed
- [x] Integrations identified (FastAPI + SQLite, no external APIs)
- [x] Source of Truth defined (PPG + Accel + Temp from hardware)
- [x] Delivery Payload specified (Web Dashboard + WebSocket)
- [x] Behavioral Rules established (immutable in gemini.md)
- [x] JSON schema written to gemini.md (4 layers defined)
- [x] Research completed (HeartPy, SciPy, Chart.js, WebSocket arch)
- [x] Blueprint approved by user

---

## ⚡ Phase 2 Checklist — Link
- [x] .env created (no external API keys needed for V1 — local only)
- [x] Link phase signed off (local-only stack: FastAPI + SQLite)

> **Note:** Phase 2 is a no-op for V1. All services are local. No external handshake required.

---

## ⚙️ Phase 3 Checklist — Architect

### SOPs (architecture/)
- [ ] `signal_processor_sop.md` — PPG ingestion, filter, HR extraction
- [ ] `baseline_engine_sop.md` — Personal baseline computation
- [ ] `alert_engine_sop.md` — Tier escalation & smoothing logic
- [ ] `api_sop.md` — FastAPI routes, WebSocket broadcast
- [ ] `database_sop.md` — SQLite schema & async ORM patterns

### Tools (tools/)
- [ ] `signal_processor.py` — Layer 0 → Layer 1 transform
- [ ] `baseline_engine.py` — Layer 1 → Layer 2 baseline update
- [ ] `alert_engine.py` — Layer 1+2 → Layer 3 alert payload
- [ ] `database.py` — SQLAlchemy models + CRUD
- [ ] `main.py` — FastAPI app entry point + WebSocket
- [ ] `simulator.py` — Synthetic sensor data for testing

### Validation
- [ ] Each tool individually tested with simulator.py
- [ ] End-to-end pipeline: simulate → ingest → process → alert → dashboard
- [ ] All errors logged in progress.md

---

## ✨ Phase 4 Checklist — Stylize
- [ ] Output payload formatted for delivery channel
- [ ] UI/dashboard built (if applicable)
- [ ] Stylized output shown to user for feedback
- [ ] User approves final format

---

## 🛰️ Phase 5 Checklist — Trigger
- [ ] Logic deployed to cloud/production
- [ ] Trigger mechanism configured (Cron/Webhook/Listener)
- [ ] Maintenance Log finalized in gemini.md
- [ ] Project marked COMPLETE
