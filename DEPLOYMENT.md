# Deployment Guide — Agentic Commerce Gateway

This guide covers deployment options, environment variables, hosting recommendations, and OAuth 2.1 configuration for running the **Agentic Commerce Gateway** in a remote environment with Claude or custom AI agents.

---

## 1. OAuth 2.1 Scope & Architecture Note

> **Design Notice**: This deployment implements an **OAuth 2.1 authorization-code flow with a single pre-registered static client** (`client_id` / `client_secret`). Dynamic Client Registration (DCR) and PKCE are intentionally out of scope for this deployment.

- **Local Mode**: Runs over `stdio` transport using `python -m app.mcp.server` with local identity resolution via `resolve_customer`.
- **Remote Mode**: Runs as a Streamable HTTP MCP server mounted at `/mcp` on the FastAPI application. Tool calls require a valid `Bearer <JWT>` access token whose `sub` claim cryptographically binds the customer identity.

---

## 2. Recommended Hosting: Render Free Tier

### Free Tier Specifications & Behaviors
- **Compute**: 0.1 CPU, 512 MB RAM.
- **Inactivity Spin-down**: Free web services sleep after 15 minutes of inactivity. The first incoming request after sleep takes 30–50 seconds to warm up.
- **Bandwidth**: 100 GB/month included.

### ⚠️ Critical Warning: Ephemeral Filesystem & SQLite Persistence
> [!WARNING]
> **Ephemeral Storage Data Loss**: Render free-tier instances use an **ephemeral disk**. When the instance restarts, sleeps, or redeploys, the local SQLite database (`gateway.db`) is **completely reset**, wiping all non-seed customer mandates and transaction audit records.
> 
> **Recommendations**:
> 1. **For Demos / Evaluation**: Clearly label the free-tier deployment as **demo-only with non-persistent audit history**.
> 2. **For Production / Persistent Audit**: Swap SQLite for a managed database (e.g. Render Managed PostgreSQL or Supabase) by configuring `DATABASE_URL` with a PostgreSQL driver (e.g. `asyncpg` / `psycopg2`).

---

## 3. Environment Variables Configuration

Set the following environment variables in your deployment dashboard (or `.env` file):

| Variable | Required | Default / Example | Purpose |
| :--- | :---: | :--- | :--- |
| `RAZORPAY_KEY_ID` | **Yes** | `rzp_test_XXXXXXXXXXXXXX` | Razorpay Test Mode Key ID. |
| `RAZORPAY_KEY_SECRET` | **Yes** | `your_test_key_secret` | Razorpay Test Mode Key Secret. |
| `ADMIN_API_KEY` | **Yes** | `dev-admin-secret-key` | Secret key protecting `/admin/customers` and `/audit` endpoints. |
| `JWT_SECRET` | **Yes** | `dev-oauth-jwt-secret-key-32chars` | Secret key used to sign and verify OAuth access tokens. |
| `OAUTH_CLIENT_ID` | Optional | `claude-desktop-client` | Pre-registered OAuth client ID for AI connector. |
| `OAUTH_CLIENT_SECRET` | Optional | `claude-demo-secret` | Pre-registered OAuth client secret for token exchange. |
| `DATABASE_URL` | Optional | `gateway.db` | Path or connection URL for the audit database. |

---

## 4. Setting Up the Claude Remote MCP Connector

When configuring Claude (or any remote MCP-compatible client) to connect to your deployed gateway:

1. **MCP Endpoint (Streamable HTTP)**:
   ```
   https://your-app-name.onrender.com/mcp
   ```
2. **OAuth Authorization URL**:
   ```
   https://your-app-name.onrender.com/oauth/authorize
   ```
3. **OAuth Token URL**:
   ```
   https://your-app-name.onrender.com/oauth/token
   ```
4. **Client Credentials**:
   - Client ID: `claude-desktop-client` (or your configured `OAUTH_CLIENT_ID`)
   - Client Secret: `claude-demo-secret` (or your configured `OAUTH_CLIENT_SECRET`)
5. **Scopes**: `purchase`

---

## 5. Security & Isolation Invariants

1. **Cryptographic Identity Binding**: In the remote path, `propose_purchase` accepts only `product_id` and `quantity`. Customer identity is extracted directly from the validated JWT `sub` claim. Parameter injection of `customer_id` is physically impossible.
2. **Razorpay Token Isolation**: The customer's OAuth token is strictly internal to the gateway. Razorpay is authenticated exclusively using the server's own `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`. Customer JWTs are **never** forwarded to payment rails.
3. **Admin Isolation**: Admin endpoints (`/admin/customers`) and audit logs (`/audit`) are strictly protected by `X-Admin-API-Key` and never exposed over the MCP tool surface.
