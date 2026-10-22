# Inventory Reorder Planner

> **Hackathon Project — Agentic AI Hackathon 2026**

Predict stockouts and prepare explainable purchase requests without over-ordering.

---

## Purpose

Collect inventory, sales history, lead time and budget data; forecast demand during the lead-time window; subtract eligible incoming stock; prepare reorder requests with human approval gates; verify results and surface stockout risks in a clear business dashboard.

## Architecture

```
frontend/          React + Vite + TypeScript  →  Vercel (Hobby)
backend/           Python + FastAPI            →  TBD (Phase 9)
supabase/          PostgreSQL schema + seed    →  Supabase Free tier
```

**AI:** Gemini API (free tier) — bounded tool use for orchestration and explanation only. All arithmetic is deterministic Python.

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- Node.js 18+
- A Supabase project (free tier)

### 1. Clone and configure

```bash
git clone <repo-url>
cd "Invertory Reorder Planner"
cp .env.example .env
# Fill in SUPABASE_URL, SUPABASE_ANON_KEY, etc. in .env
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:5173

### 4. Tests

```bash
cd backend
pytest tests/ -v
```

## Environment Variables

See `.env.example` for all variable names. Never commit real values.

| Variable | Where used | Purpose |
|----------|-----------|---------|
| `SUPABASE_URL` | Backend | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend only | Admin DB access |
| `GEMINI_API_KEY` | Backend only | Gemini API (Phase 6) |
| `VITE_SUPABASE_URL` | Frontend | Supabase URL (public) |
| `VITE_SUPABASE_ANON_KEY` | Frontend | Supabase anon key |
| `VITE_API_BASE_URL` | Frontend | FastAPI base URL |

## Screens

1. Sign In / Sign Up (Supabase Auth)
2. Dashboard — stockout risks, pending approvals, recent requests
3. Inventory — SKUs, stock, sales rate, lead time, supplier, pack size
4. Reorder Analysis — forecast, incoming orders, shortfall, cost, evidence
5. Approval Queue — approve / reject proposed requests
6. Request Detail — request ID, status history, audit evidence
7. Test Scenarios — TC1–TC4 with input, expected and actual results

## Test Cases

| Case | Scenario |
|------|----------|
| TC1 | Low stock, no incoming order → correct reorder quantity |
| TC2 | Supplier sells in cases of 12 → quantity rounded to whole cases |
| TC3 | Pending order exists → eligible incoming stock subtracted; no duplicate |
| TC4 | Supplier price increases 20% → cost recalculated; budget review triggered |

## Build Status

See [BUILD_STATUS.md](./BUILD_STATUS.md).
