# AI Buyer Agent / Agentic Commerce Gateway

A merchant-side FastAPI architecture that allows AI shopping agents to transact on behalf of users in a bounded, auditable, policy-gated way.

> **Core Architectural Principle**: An AI agent may only ever **propose** a purchase, never authorize one. A deterministic Policy / Mandate Engine acts as the non-bypassable boundary between proposal and payment.

> **OAuth 2.1 Identity Architecture**: OAuth 2.1 authorization-code flow with a single pre-registered client; Dynamic Client Registration and PKCE intentionally out of scope for this deployment. Identity in remote Streamable HTTP mode is bound strictly to the verified JWT `sub` claim. Local `stdio` mode with `resolve_customer` is preserved for local single-user development.

---

## Project Structure

```
ai-buyer-gateway/
├── app/
│   ├── main.py                  # FastAPI app entrypoint & logging configuration
│   ├── auth.py                  # Admin API key authentication dependency
│   ├── exceptions.py            # Transport-agnostic domain exceptions
│   ├── admin/
│   │   ├── models.py            # Admin request schemas (mandate creation/updating)
│   │   └── router.py            # Admin-only customer and mandate management endpoints
│   ├── catalog/
│   │   ├── models.py            # Product Pydantic schema
│   │   ├── data.py              # In-memory seed catalog; MERCH_ELEC + MERCH_FOOD products
│   │   ├── service.py           # Catalog search and lookup service
│   │   └── router.py            # GET /products, /products/{id}
│   ├── agent/
│   │   ├── service.py           # Core purchase execution service with idempotency and stock checks
│   │   └── router.py            # POST /agent/purchase — HTTP wrapper with domain error mapping
│   ├── mcp/
│   │   ├── tools.py             # propose_purchase and search_products MCP tools
│   │   └── server.py            # Stdio MCP server for Claude Desktop / LLM clients
│   ├── policy/
│   │   ├── mandate.py           # Mandate schema and expiration verification
│   │   ├── engine.py            # Pure evaluate() rule engine
│   │   ├── requests.py          # PurchaseRequest & PolicyDecision models
│   │   └── store.py             # Thread-safe in-memory customer mandate store
│   ├── payment/
│   │   ├── models.py            # PaymentResult Pydantic model
│   │   ├── razorpay_client.py   # Lazy singleton Razorpay SDK wrapper
│   │   └── service.py           # create_order_for_approved(); rupee→paise conversion & error sanitization
│   └── audit/
│       ├── models.py            # AuditRecord Pydantic schema
│       ├── store.py             # AuditStore SQLite persistence with two-phase writes & connection closing
│       └── router.py            # GET /audit, GET /audit/{transaction_id}
├── tests/
│   ├── conftest.py              # Shared autouse SQLite DB isolation & mandate store resets
│   ├── test_admin.py            # Admin endpoint and authentication tests
│   ├── test_agent_router.py     # Agent purchase API integration, stock check & idempotency tests
│   ├── test_audit.py            # Audit trail store, PENDING state, and query endpoint tests
│   ├── test_catalog.py          # Catalog endpoint and search tests
│   ├── test_mcp.py              # Model Context Protocol (MCP) server, tool & error handling tests
│   ├── test_payments.py         # Razorpay payment integration & paise conversion tests
│   └── test_policy_engine.py    # Policy engine rule evaluation & expiration boundary tests
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
ADMIN_API_KEY=dev-admin-secret-key
```
> ⚠️ **Test Mode only.** Keys starting with `rzp_test_` never move real money.
> Obtain test keys from the [Razorpay Dashboard → Settings → API Keys](https://dashboard.razorpay.com/).

### 3. Run Tests
```powershell
# Default run — all mocked, no live network calls or db pollution
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

| Method | Path | Description | Access Level |
| :----- | :--- | :---------- | :----------- |
| `GET` | `/health` | Service health check | Public / System |
| `GET` | `/products` | List catalog products (filter by `query`, `category`, `max_price`) | Public / AI |
| `GET` | `/products/{id}` | Get single product by ID (`KB001`, `MN001`, `FD001`, etc.) | Public / AI |
| `POST` | `/agent/purchase` | Propose an agent purchase — policy evaluation + audit logging + Razorpay order creation (supports `idempotency_key`) | System / API |
| `POST` | `/admin/customers` | Provision a new dynamic customer mandate | **Admin Only** (`X-Admin-API-Key` required) |
| `GET` | `/admin/customers` | List all customer mandates | **Admin Only** (`X-Admin-API-Key` required) |
| `GET` | `/admin/customers/{id}` | Get single customer mandate | **Admin Only** (`X-Admin-API-Key` required) |
| `PATCH` | `/admin/customers/{id}/mandate` | Update customer spending limit | **Admin Only** (`X-Admin-API-Key` required) |
| `GET` | `/audit` | List all audit records (filter by `customer_id`, `decision`) | **Admin Only** (`X-Admin-API-Key` required) |
| `GET` | `/audit/{transaction_id}` | Get a single audit record by its transaction ID | **Admin Only** (`X-Admin-API-Key` required) |

---

## MCP Tools (AI-Facing Surface)

The gateway exposes a native Model Context Protocol (MCP) server over **stdio transport**, allowing AI clients (like **Claude Desktop**) to search the catalog and propose purchases.

### 1. `search_products`
Enables the AI shopping agent to resolve customer search intents (e.g. "I want a keyboard") to exact product IDs before proposing a purchase.
- **Inputs**:
  - `query` (optional string): Case-insensitive substring search on product name.
  - `category` (optional string): Case-insensitive exact match on category.
  - `max_price` (optional float): Maximum price upper bound in INR (₹).
- **Output**: Array of `{ "id": str, "name": str, "category": str, "price": float }`.
- **AI Instruction**: *"Call this before `propose_purchase` whenever you don't already have an exact product ID. Never ask the customer for a product ID directly — search for it."*

### 2. `propose_purchase`
Submits a purchase proposal for deterministic policy evaluation and Razorpay Test Mode order creation.
- **Inputs**: `customer_id` (str), `product_id` (str), `quantity` (int, default: 1).
- **Output**: Minimized customer-facing dictionary (see Data Minimization section below).
- **AI Instruction**: *"This only proposes a purchase for policy evaluation — it does not guarantee approval. The Policy Engine independently verifies the mandate."*

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

## Security & Data Minimization

### 1. Presentation-Layer Data Minimization
AI models can unintentionally leak internal system identifiers, order IDs, or database keys into natural language conversations. The gateway enforces **code-level data minimization** at the MCP boundary via `to_customer_response()`:

```json
{
  "decision": "APPROVED",
  "product_name": "Mechanical Gaming Keyboard",
  "amount": 1499.0,
  "reason": "Transaction amount ₹1499.00 is within mandate limit of ₹2000.00 and meets all policy criteria",
  "reference_code": "REF-ABC12345"
}
```

> **Security Guarantee**: *"The AI never receives raw `transaction_id` UUIDs or `razorpay_order_id` values — it physically cannot leak what it was never given."*

### 2. Admin & Audit Endpoint Authentication
Mandate provisioning (`POST /admin/customers`), spending limit modification (`PATCH /admin/customers/{id}/mandate`), and audit logs (`GET /audit`) are strictly protected via `X-Admin-API-Key` or `Authorization: Bearer <key>`. They are **never registered as MCP tools** or exposed unauthenticated.

### 3. Preserved Admin Traceability
Data minimization applies only to the AI-facing presentation layer. The underlying SQLite audit store continues to record complete end-to-end telemetry (UUIDs, merchant IDs, Razorpay order IDs, timestamps), queryable via `GET /audit/{transaction_id}`.

---

## Audit Trail & State Transitions

Every purchase evaluation writes an immutable record to SQLite:
1. **Phase A (Always)**: Captured immediately after policy evaluation — logs the proposal details (`customer_id`, `product_id`, `quantity`, `amount`), the verdict (`APPROVED` / `REJECTED`), and the explicit human-readable `decision_reason`. For approved proposals, `payment_status` is initialized to `'PENDING'`.
2. **Phase B (On Approval)**: Updated with the downstream payment execution outcome (`payment_status='created'` or `'failed'`, `razorpay_order_id`).

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
  "decision_reason": "Transaction amount ₹1499.00 is within mandate limit of ₹2000.00 and meets all policy criteria",
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
  "decision_reason": "Transaction amount ₹4999.00 exceeds maximum mandate limit of ₹2000.00",
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
