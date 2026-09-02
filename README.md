# AI Buyer Agent / Agentic Commerce Gateway

A merchant-side FastAPI architecture that allows AI shopping agents to transact on behalf of users in a bounded, auditable, policy-gated way.

> **Core Architectural Principle**: An AI agent may only ever **propose** a purchase, never authorize one. A deterministic Policy / Mandate Engine acts as the non-bypassable boundary between proposal and payment.
> 
> **Two-Step Confirmation Gating**: Micro-transactions ($< ₹500$) auto-execute under user mandates; transactions $\ge ₹500$ generate short-lived, cryptographically signed JWT confirmation tokens requiring human authorization before payment execution.
> 
> **OAuth 2.1 Identity Architecture**: OAuth 2.1 authorization-code flow with Bearer JWT tokens binding strictly to the verified `sub` claim. Local `stdio` mode with `resolve_customer` is preserved for local single-user development.

---

## Project Structure

```
ai-buyer-gateway/
├── app/
│   ├── main.py                  # FastAPI app entrypoint & logging configuration
│   ├── auth.py                  # OAuth JWT & Admin API key authentication dependencies
│   ├── exceptions.py            # Transport-agnostic domain exceptions
│   ├── admin/
│   │   ├── models.py            # Admin request schemas (mandate creation/updating)
│   │   └── router.py            # Admin-only customer and mandate management endpoints
│   ├── catalog/
│   │   ├── models.py            # Product Pydantic schema
│   │   ├── data.py              # In-memory seed catalog; MERCH_ELEC + MERCH_FOOD products
│   │   ├── service.py           # Catalog search, lookup, and stock management service
│   │   └── router.py            # GET /products, /products/{id}
│   ├── agent/
│   │   ├── service.py           # Purchase execution, confirmation tokens, and stock decrement
│   │   └── router.py            # POST /agent/purchase, POST /agent/confirm (Auth protected)
│   ├── merchant_agent/
│   │   ├── models.py            # InquiryRequest, ProductQuote, AddOnRecommendation schemas
│   │   ├── service.py           # Gemini 2.5 Flash reasoning, quote grounding & smart add-on engine
│   │   └── router.py            # POST /merchant/inquire, POST /merchant/recommend-addons
│   ├── mcp/
│   │   ├── tools.py             # propose_purchase, confirm_purchase, suggest_addons MCP tools
│   │   └── server.py            # Stdio MCP server for Claude Desktop / LLM clients
│   ├── policy/
│   │   ├── mandate.py           # Mandate schema (max_transaction_amount, daily_limit, expiry)
│   │   ├── engine.py            # Pure evaluate() deterministic rule engine
│   │   ├── requests.py          # PurchaseRequest & PolicyDecision models
│   │   └── store.py             # SQLite customer mandate store with daily spending tracking
│   ├── payment/
│   │   ├── models.py            # PaymentResult Pydantic model
│   │   ├── razorpay_client.py   # Lazy singleton Razorpay SDK wrapper
│   │   └── service.py           # create_order_for_approved(); rupee→paise conversion & error isolation
│   └── audit/
│       ├── models.py            # AuditRecord schema with SHA-256 prev_hash & record_hash
│       ├── store.py             # Hash-chained audit store with integrity verification
│       └── router.py            # GET /audit, GET /audit/{tx_id}, GET /audit/verify
├── tests/
│   ├── conftest.py              # Shared autouse SQLite DB isolation & mandate store resets
│   ├── test_admin.py            # Admin endpoint and authentication tests
│   ├── test_agent_router.py     # Agent purchase API, auth, confirmation tokens & error tests
│   ├── test_audit.py            # Audit trail store, SHA-256 hash chaining & GET /audit/verify tests
│   ├── test_catalog.py          # Catalog endpoint, search & stock management tests
│   ├── test_mcp.py              # Local MCP server, tools, confirmation flow & idempotency tests
│   ├── test_mcp_remote.py       # Streamable HTTP MCP, OAuth bearer auth & token isolation tests
│   ├── test_merchant_agent.py   # Gemini LLM reasoning, quote grounding & add-on upsell tests
│   ├── test_oauth.py            # OAuth 2.1 token issuance, refresh rotation & password hashing tests
│   ├── test_payments.py         # Razorpay payment integration & paise conversion tests
│   ├── test_policy_engine.py    # Policy engine rule evaluation & cumulative daily limit tests
│   └── test_google_oauth_and_signup.py # Google login redirect & auto-provisioning tests
├── .env.example                 # Environment variables template
├── requirements.txt             # Pinned project dependencies
└── README.md
```

---

## Quickstart

### 1. Environment Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
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
GEMINI_API_KEY=your_gemini_api_key_here
```
> ⚠️ **Test Mode only.** Keys starting with `rzp_test_` never move real money.

### 3. Run Tests
```powershell
# Default run — 150 passed automated tests
.\.venv\Scripts\pytest.exe -v
```

### 4. Start Development Server
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## Active API Endpoints

| Method | Path | Description | Access Level |
| :----- | :--- | :---------- | :----------- |
| `GET` | `/health` | Service health check | Public / System |
| `GET` | `/products` | List catalog products (filter by `query`, `category`, `max_price`) | Public / AI |
| `GET` | `/products/{id}` | Get single product by ID (`KB001`, `MN001`, `FD001`, etc.) | Public / AI |
| `POST` | `/agent/purchase` | Propose a purchase — returns `PENDING_CONFIRMATION` for $\ge ₹500$ or executes for $< ₹500$ | **Authenticated** (JWT / Admin Key) |
| `POST` | `/agent/confirm` | Authorize and execute a pending purchase via signed confirmation token | **Authenticated** (JWT / Admin Key) |
| `POST` | `/merchant/inquire` | Natural language inquiry to Gemini Merchant AI | Public / Buyer AI |
| `POST` | `/merchant/recommend-addons` | Recommend smart complementary add-ons within budget headroom | Public / Buyer AI |
| `POST` | `/admin/customers` | Provision a new dynamic customer mandate & OAuth credentials | **Admin Only** (`X-Admin-API-Key`) |
| `GET` | `/admin/customers` | List all customer mandates | **Admin Only** (`X-Admin-API-Key`) |
| `GET` | `/admin/customers/{id}` | Get single customer mandate | **Admin Only** (`X-Admin-API-Key`) |
| `PATCH` | `/admin/customers/{id}/mandate` | Update customer spending limit | **Admin Only** (`X-Admin-API-Key`) |
| `GET` | `/audit` | List all audit records (filter by `customer_id`, `decision`) | **Admin Only** (`X-Admin-API-Key`) |
| `GET` | `/audit/{tx_id}` | Get single audit record with cryptographic hash metadata | **Admin Only** (`X-Admin-API-Key`) |
| `GET` | `/audit/verify` | Verify SHA-256 cryptographic chain integrity across entire ledger | **Admin Only** (`X-Admin-API-Key`) |

---

## MCP Tools (AI-Facing Surface)

The gateway exposes a native Model Context Protocol (MCP) server over **stdio transport** and **Streamable HTTP**, allowing AI clients (like **Claude Desktop**) to search the catalog, inquire for quotes, and propose purchases.

### 1. `inquire_merchant`
Consults the Gemini Merchant Sales Agent with natural language requirements.

### 2. `suggest_addons`
Discovers complementary cross-sell add-ons that fit within the customer's remaining mandate budget headroom.

### 3. `propose_purchase`
Submits a purchase proposal for deterministic policy evaluation.
- For items $< ₹500$: Auto-executes payment under mandate.
- For items $\ge ₹500$: Returns `PENDING_CONFIRMATION` with a signed 5-minute JWT confirmation token.

### 4. `confirm_purchase`
Executes an approved purchase proposal using a valid confirmation token.

### 5. `search_products`
Keyword-based catalog search tool with category and price filters.

### 6. `resolve_customer`
Discovers customer profile IDs from human names or email addresses.

---

## Cryptographic Audit Trail & Integrity Verification

Every purchase evaluation writes an immutable record to SQLite with SHA-256 hash chaining:
$$\text{record\_hash} = \text{SHA256}(\text{transaction\_id} \mathbin{\Vert} \text{timestamp} \mathbin{\Vert} \text{customer\_id} \mathbin{\Vert} \text{product\_id} \mathbin{\Vert} \text{amount} \mathbin{\Vert} \text{decision} \mathbin{\Vert} \text{razorpay\_order\_id} \mathbin{\Vert} \text{prev\_hash})$$

Admins can verify ledger integrity at any time via:
```bash
curl -H "X-Admin-API-Key: dev-admin-secret-key" http://127.0.0.1:8000/audit/verify
```
Response:
```json
{
  "total_records": 42,
  "tamper_detected": false,
  "verified_at": "2026-09-02T16:30:00Z",
  "status": "SECURE"
}
```

---

## Test Suite Summary

The project includes **150 automated tests** covering all units, integrations, security boundaries, and payment flows:
```powershell
.\.venv\Scripts\pytest.exe -v
# 150 passed in 85.38s (100% pass rate)
```
