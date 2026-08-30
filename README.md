# AI Buyer Agent / Agentic Commerce Gateway

A merchant-side FastAPI architecture that allows AI shopping agents to transact on behalf of users in a bounded, auditable, policy-gated way.

> **Core Architectural Principle**: An AI agent may only ever **propose** a purchase, never authorize one. A deterministic Policy / Mandate Engine acts as the non-bypassable boundary between proposal and payment.

---

## Project Structure

```
ai-buyer-gateway/
├── app/
│   ├── main.py                  # FastAPI app entrypoint
│   ├── catalog/
│   │   ├── models.py            # Product Pydantic schema (Phase 1)
│   │   ├── data.py              # In-memory seed catalog; MERCH_ELEC + MERCH_FOOD products (Phase 1 + Piece A)
│   │   └── router.py            # GET /products, /products/{id} (Phase 1)
│   ├── agent/
│   │   ├── agent.py             # (Phase 4 placeholder)
│   │   └── router.py            # POST /agent/purchase — orchestration layer (Phase 3)
│   ├── policy/
│   │   ├── mandate.py           # Mandate schema (Phase 2)
│   │   ├── engine.py            # Pure evaluate() rule engine (Phase 2)
│   │   ├── requests.py          # PurchaseRequest & PolicyDecision models (Phase 2)
│   │   └── store.py             # Per-customer mandate store; CUST001 & CUST002 (Phase 2)
│   ├── payment/
│   │   ├── models.py            # PaymentResult Pydantic model (Phase 5)
│   │   ├── razorpay_client.py   # Lazy singleton Razorpay SDK wrapper — sole SDK import (Phase 5)
│   │   └── service.py           # create_order_for_approved(); rupee→paise conversion (Phase 5)
│   ├── audit/
│   │   ├── models.py            # (Phase 6 placeholder)
│   │   └── logger.py            # (Phase 6 placeholder)
│   └── db.py                    # (Persistence placeholder)
├── tests/
│   ├── test_catalog.py          # Catalog endpoint tests (Phase 1)
│   ├── test_policy_engine.py    # Policy engine rule evaluation tests (Phase 2)
│   ├── test_agent_router.py     # Agent purchase API integration tests (Phase 3 + Piece A)
│   └── test_payments.py         # Razorpay payment integration tests (Phase 5)
├── .env.example                 # Environment variables template
├── requirements.txt             # Project dependencies
└── README.md
```

---

## Quickstart

### 1. Environment Setup
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your **Razorpay Test Mode** keys:
```powershell
Copy-Item .env.example .env
```
Then edit `.env`:
```
RAZORPAY_KEY_ID=rzp_test_your_key_id_here
RAZORPAY_KEY_SECRET=your_test_key_secret_here
```
> ⚠️ **Test Mode only.** Keys starting with `rzp_test_` never move real money.
> Obtain test keys from the [Razorpay Dashboard → Settings → API Keys](https://dashboard.razorpay.com/).

### 3. Run Tests
```powershell
# Default run — all mocked, no network calls required
.venv\Scripts\pytest.exe -v

# Integration test only — requires real Test Mode keys in .env
.venv\Scripts\pytest.exe -v -m integration
```

### 4. Start Development Server
```powershell
uvicorn app.main:app --reload
```

---

## Active API Endpoints

| Method | Path | Description |
| :----- | :--- | :---------- |
| `GET` | `/health` | Service health check |
| `GET` | `/products` | List catalog products (filter by `category`, `max_price`) |
| `GET` | `/products/{id}` | Get single product by ID (`KB001`, `MN001`, `FD001`, etc.) |
| `POST` | `/agent/purchase` | Propose an agent purchase — policy evaluation + Razorpay order creation |

### `POST /agent/purchase` — Request / Response

**Request body:**
```json
{
  "customer_id": "CUST001",
  "product_id": "KB001",
  "quantity": 1
}
```

**Response (APPROVED):**
```json
{
  "decision": "APPROVED",
  "reason": "Transaction amount ₹1499.00 is within mandate limit of ₹2000.00 ...",
  "product_id": "KB001",
  "amount": 1499.0,
  "mandate_limit": 2000.0,
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "payment": {
    "status": "created",
    "razorpay_order_id": "order_ABC123...",
    "error": null
  }
}
```

**Response (REJECTED):**
```json
{
  "decision": "REJECTED",
  "reason": "Transaction amount ₹4999.00 exceeds maximum mandate limit ...",
  "product_id": "MN001",
  "amount": 4999.0,
  "mandate_limit": 2000.0,
  "transaction_id": "550e8400-e29b-41d4-a716-446655440001",
  "payment": null
}
```

---

## Phase 5 — Razorpay Test Mode Integration

### What Phase 5 does
- On a **policy-APPROVED** purchase, creates a real Razorpay Test Mode order via `POST /agent/purchase`.
- The `transaction_id` (UUID4) minted by the gateway is passed as Razorpay's `receipt` field for cross-system tracing.
- Amount is converted from INR rupees → paise inside `app/payment/service.py` only — this conversion does not touch `app/catalog/` or `app/policy/`.
- A Razorpay SDK failure returns `payment.status = "failed"` in the response — it never alters the `PolicyDecision` or causes an HTTP 500.

### What is explicitly OUT OF SCOPE for Phase 5
The following features are intentionally deferred to later phases:

- **Checkout frontend** — no payment UI, redirect flows, or Razorpay Checkout JS.
- **Payment capture** — order creation uses `payment_capture: 1` (auto-capture). Manual capture is not implemented.
- **Signature verification** — Razorpay webhook signature validation is not implemented.
- **Webhooks** — no webhook endpoint or event handling.
- **Refunds** — no refund initiation or tracking.

---

## Demo Mandate Data

| Customer | Mandate Limit | Allowed Merchants | Allowed Categories |
| :------- | :------------ | :---------------- | :----------------- |
| `CUST001` | ₹2,000 | `MERCH_ELEC`, `MERCH_FOOD` | electronics, home_kitchen, apparel, food |
| `CUST002` | ₹1,500 | `MERCH_ELEC` only | electronics, home_kitchen |

### Canonical Demo Products

| ID | Name | Price | Merchant | Expected Decision (CUST001) |
| :- | :--- | ----: | :------- | :-------------------------- |
| `KB001` | Mechanical Gaming Keyboard | ₹1,499 | MERCH_ELEC | ✅ APPROVED |
| `MN001` | 27-inch 4K UHD Monitor | ₹4,999 | MERCH_ELEC | ❌ REJECTED (over limit) |
| `FD001` | Cold-Pressed Virgin Coconut Oil | ₹349 | MERCH_FOOD | ✅ APPROVED |
| `FD002` | Organic Rolled Oats | ₹299 | MERCH_FOOD | ✅ APPROVED |
