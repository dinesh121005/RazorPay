# AI Buyer Agent / Agentic Commerce Gateway

A merchant-side FastAPI architecture that allows AI shopping agents to transact on behalf of users in a bounded, auditable, policy-gated way.

> **Core Architectural Principle**: An AI agent may only ever **propose** a purchase, never authorize one. A deterministic Policy / Mandate Engine acts as the non-bypassable boundary between proposal and payment.

---

## Project Structure

```
ai-buyer-gateway/
├── app/
│   ├── main.py                  # FastAPI app entrypoint (mounts catalog & /health)
│   ├── catalog/
│   │   ├── models.py            # Product Pydantic schema (Phase 1)
│   │   ├── data.py              # In-memory seed catalog with fixed demo IDs (Phase 1)
│   │   └── router.py            # GET /products, /products/{id} (Phase 1)
│   ├── agent/
│   │   ├── agent.py             # (Phase 4 placeholder)
│   │   └── router.py            # (Phase 3 placeholder)
│   ├── policy/
│   │   ├── mandate.py           # Mandate schema & CUST001 demo mandate (Phase 2)
│   │   ├── engine.py            # Pure evaluate() rule engine (Phase 2)
│   │   ├── requests.py          # PurchaseRequest & PolicyDecision models (Phase 2)
│   │   └── store.py             # Per-customer mandate store (Phase 2)
│   ├── payment/
│   │   ├── razorpay_client.py   # (Phase 5 placeholder)
│   │   └── service.py           # (Phase 5 placeholder)
│   ├── audit/
│   │   ├── models.py            # (Phase 6 placeholder)
│   │   └── logger.py            # (Phase 6 placeholder)
│   └── db.py                    # (Persistence placeholder)
├── tests/
│   ├── test_catalog.py          # Catalog endpoints & filtering tests (Phase 1)
│   └── test_policy_engine.py    # Policy engine rule evaluation tests (Phase 2)
├── .env.example                 # Environment variables template
├── requirements.txt             # Project dependencies
└── README.md                    # Documentation
```

---

## Quickstart

### 1. Environment Setup
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Run Tests
```powershell
pytest tests/ -v
```

### 3. Start Development Server
```powershell
uvicorn app.main:app --reload
```

---

## Active API Endpoints (Phases 1 & 2)

- `GET /health` — Service health check
- `GET /products` — List catalog products (supports `category` and `max_price` query parameters)
- `GET /products/{id}` — Get single product by ID (`KB001`, `MN001`, etc.)
