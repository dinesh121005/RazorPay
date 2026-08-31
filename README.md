# AI Buyer Agent / Agentic Commerce Gateway

A merchant-side FastAPI architecture that allows AI shopping agents to transact on behalf of users in a bounded, auditable, policy-gated way.

> **Core Architectural Principle**: An AI agent may only ever **propose** a purchase, never authorize one. A deterministic Policy / Mandate Engine acts as the non-bypassable boundary between proposal and payment.

---

## Project Structure

```
ai-buyer-gateway/
├── app/
│   ├── main.py                  # FastAPI app entrypoint (mounts catalog, agent, and audit routers)
│   ├── catalog/
│   │   ├── models.py            # Product Pydantic schema (Phase 1)
│   │   ├── data.py              # In-memory seed catalog; MERCH_ELEC + MERCH_FOOD products (Phase 1 + Piece A)
│   │   └── router.py            # GET /products, /products/{id} (Phase 1)
│   ├── agent/
│   │   ├── service.py           # Core purchase execution service layer (Phase 4)
│   │   └── router.py            # POST /agent/purchase — thin HTTP wrapper around service (Phase 3 + Phase 4)
│   ├── mcp/
│   │   ├── tools.py             # propose_purchase MCP tool calling service.execute_purchase (Phase 4)
│   │   └── server.py            # Stdio MCP server for Claude Desktop (Phase 4)
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
│   │   ├── models.py            # AuditRecord Pydantic schema (Phase 6)
│   │   ├── store.py             # AuditStore SQLite persistence with two-phase writes (Phase 6)
│   │   └── router.py            # GET /audit, GET /audit/{transaction_id} (Phase 6)
│   └── db.py                    # (Persistence placeholder)
├── tests/
│   ├── test_catalog.py          # Catalog endpoint tests (Phase 1)
│   ├── test_policy_engine.py    # Policy engine rule evaluation tests (Phase 2)
│   ├── test_agent_router.py     # Agent purchase API integration tests (Phase 3 + Piece A)
│   ├── test_payments.py         # Razorpay payment integration tests (Phase 5)
│   ├── test_audit.py            # Audit trail store and query endpoint tests (Phase 6)
│   └── test_mcp.py              # Model Context Protocol (MCP) server & tool tests (Phase 4)
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
DATABASE_URL=gateway.db
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
| `POST` | `/agent/purchase` | Propose an agent purchase — policy evaluation + audit logging + Razorpay order creation |
| `GET` | `/audit` | List all audit records (filter by `customer_id`, `decision`) |
| `GET` | `/audit/{transaction_id}` | Get a single audit record by its transaction ID |

---

## Phase 4 — Model Context Protocol (MCP) Integration

The gateway exposes a native MCP server over **stdio transport**, enabling AI clients like **Claude Desktop** to invoke the purchase workflow as an agentic tool.

### Exposed MCP Tool
- **`propose_purchase`**: Propose a purchase under customer spending mandates.
  - **Inputs**: `customer_id` (str), `product_id` (str), `quantity` (int, default: 1).
  - **Outputs**: Policy verdict (`APPROVED` / `REJECTED`), rule explanation, transaction UUID, computed amount, and Razorpay order ID.

### Connecting Claude Desktop
Add the gateway to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "ai-buyer-gateway": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "D:\\RazorPay",
      "env": {
        "RAZORPAY_KEY_ID": "rzp_test_your_key_id",
        "RAZORPAY_KEY_SECRET": "your_key_secret",
        "DATABASE_URL": "gateway.db"
      }
    }
  }
}
```

---

## Phase 6 — Audit Trail with SQLite

"Show the audit trail" is a core judging criterion. Every call to `POST /agent/purchase` writes an immutable record to SQLite:
1. **Phase A (Always)**: Captured immediately after policy evaluation — logs the proposal details (`customer_id`, `product_id`, `quantity`, `amount`), the verdict (`APPROVED` / `REJECTED`), and the explicit human-readable `decision_reason`.
2. **Phase B (On Approval)**: Updated with the downstream payment execution outcome (`payment_status`, `razorpay_order_id`).

### Audit Record Examples

#### 1. Approved Purchase Audit Record (`GET /audit/{transaction_id}`)
```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-08-30T10:15:30.123456+00:00",
  "customer_id": "CUST001",
  "product_id": "KB001",
  "merchant_id": "MERCH_ELEC",
  "quantity": 1,
  "amount": 1499.0,
  "decision": "APPROVED",
  "decision_reason": "Transaction amount ₹1499.00 is within mandate limit of ₹2000.00.",
  "payment_status": "created",
  "razorpay_order_id": "order_TW0f49Ev2HnwLD"
}
```

#### 2. Rejected Purchase Audit Record (`GET /audit/{transaction_id}`)
```json
{
  "transaction_id": "550e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2026-08-30T10:16:45.654321+00:00",
  "customer_id": "CUST001",
  "product_id": "MN001",
  "merchant_id": "MERCH_ELEC",
  "quantity": 1,
  "amount": 4999.0,
  "decision": "REJECTED",
  "decision_reason": "Transaction amount ₹4999.00 exceeds maximum mandate limit of ₹2000.00.",
  "payment_status": null,
  "razorpay_order_id": null
}
```

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
