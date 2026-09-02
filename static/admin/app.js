/**
 * Agentic Commerce Gateway — Admin Dashboard JavaScript Controller
 */

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

class AdminDashboard {
  constructor() {
    this.adminKey = localStorage.getItem("admin_api_key") || "dev-admin-secret-key";
    this.auditRecords = [];
    this.mandates = [];
    this.products = [];
    this.autoRefreshEnabled = false; // Default OFF to keep logs clean
    this.autoRefreshTimer = null;
    this.countdownSeconds = 15;
    this.currentTab = "overview";

    this.initElements();
    this.bindEvents();
    this.updateKeyLabel();
    this.fetchAllData();
  }

  initElements() {
    // Navigation
    this.navItems = document.querySelectorAll(".nav-item");
    this.tabPanes = document.querySelectorAll(".tab-pane");

    // KPI elements
    this.kpiTotalVolume = document.getElementById("kpi-total-volume");
    this.kpiApprovedCount = document.getElementById("kpi-approved-count");
    this.kpiTotalTx = document.getElementById("kpi-total-tx");
    this.kpiApprovalRate = document.getElementById("kpi-approval-rate");
    this.kpiProgress = document.getElementById("kpi-progress");
    this.kpiMandateCount = document.getElementById("kpi-mandate-count");
    this.auditCountBadge = document.getElementById("audit-count-badge");
    this.lastSyncedLabel = document.getElementById("last-synced-label");

    // Tables
    this.recentTbody = document.getElementById("recent-transactions-tbody");
    this.auditTbody = document.getElementById("audit-full-tbody");
    this.mandatesTbody = document.getElementById("mandates-tbody");
    this.catalogGrid = document.getElementById("catalog-grid");

    // Filters
    this.auditSearch = document.getElementById("audit-filter-search");
    this.auditDecisionFilter = document.getElementById("audit-filter-decision");
    this.auditCustomerFilter = document.getElementById("audit-filter-customer");
    this.clearFiltersBtn = document.getElementById("clear-filters-btn");

    // Sandbox
    this.sandboxPrompt = document.getElementById("sandbox-prompt");
    this.sandboxBudget = document.getElementById("sandbox-budget");
    this.sandboxQty = document.getElementById("sandbox-qty");
    this.sandboxCustomerSelect = document.getElementById("sandbox-customer-select");
    this.sandboxConsole = document.getElementById("sandbox-console");
    this.sandboxStatusPill = document.getElementById("sandbox-status-pill");
    this.inquireBtn = document.getElementById("run-a2a-inquiry-btn");
    this.purchaseBtn = document.getElementById("run-a2a-purchase-btn");
    this.quickChips = document.querySelectorAll(".chip");

    // Refresh & Auth
    this.refreshBtn = document.getElementById("refresh-btn");
    this.refreshIcon = document.getElementById("refresh-icon");
    this.autoRefreshToggle = document.getElementById("auto-refresh-toggle");
    this.authPill = document.getElementById("auth-pill");
    this.activeKeyLabel = document.getElementById("active-key-label");

    // Modals
    this.mandateModal = document.getElementById("mandate-modal");
    this.newCustomerModal = document.getElementById("new-customer-modal");
    this.txDetailModal = document.getElementById("tx-detail-modal");
    this.authKeyModal = document.getElementById("auth-key-modal");
    this.txDetailJson = document.getElementById("tx-detail-json");
  }

  bindEvents() {
    // Tab switching
    this.navItems.forEach((item) => {
      item.addEventListener("click", () => {
        const tab = item.getAttribute("data-tab");
        this.switchTab(tab);
      });
    });

    document.querySelectorAll("[data-goto-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.getAttribute("data-goto-tab");
        this.switchTab(tab);
      });
    });

    // Refresh button
    if (this.refreshBtn) {
      this.refreshBtn.addEventListener("click", () => {
        this.fetchAllData();
      });
    }

    // Auto-refresh toggle
    if (this.autoRefreshToggle) {
      this.autoRefreshToggle.addEventListener("change", (e) => {
        this.autoRefreshEnabled = e.target.checked;
        if (this.autoRefreshEnabled) {
          this.startAutoRefresh();
          this.showToast("Live auto-refresh enabled (15s)", "info");
        } else {
          this.stopAutoRefresh();
          this.showToast("Live auto-refresh paused", "info");
        }
      });
    }

    // Filter events
    if (this.auditSearch) this.auditSearch.addEventListener("input", () => this.renderAuditTable());
    if (this.auditDecisionFilter) this.auditDecisionFilter.addEventListener("change", () => this.renderAuditTable());
    if (this.auditCustomerFilter) this.auditCustomerFilter.addEventListener("change", () => this.renderAuditTable());
    if (this.clearFiltersBtn) {
      this.clearFiltersBtn.addEventListener("click", () => {
        this.auditSearch.value = "";
        this.auditDecisionFilter.value = "";
        this.auditCustomerFilter.value = "";
        this.renderAuditTable();
      });
    }

    // Sandbox quick chips
    this.quickChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        this.sandboxPrompt.value = chip.getAttribute("data-prompt");
      });
    });

    // Sandbox actions
    if (this.inquireBtn) this.inquireBtn.addEventListener("click", () => this.runSandboxInquiry());
    if (this.purchaseBtn) this.purchaseBtn.addEventListener("click", () => this.runSandboxPurchase());
    const quickTest = document.getElementById("quick-test-btn");
    if (quickTest) {
      quickTest.addEventListener("click", () => {
        this.switchTab("sandbox");
        this.sandboxPrompt.value = "i want a mechanical keyboard under 2000";
      });
    }

    // Modal triggers & closes
    document.querySelectorAll("[data-close-modal]").forEach((el) => {
      el.addEventListener("click", () => {
        const modalId = el.getAttribute("data-close-modal");
        this.closeModal(modalId);
      });
    });

    const openNewCustBtn = document.getElementById("open-new-customer-modal");
    if (openNewCustBtn) openNewCustBtn.addEventListener("click", () => this.openModal("new-customer-modal"));

    if (this.authPill) {
      this.authPill.addEventListener("click", () => {
        document.getElementById("input-admin-key").value = this.adminKey;
        this.openModal("auth-key-modal");
      });
    }

    // Save Handlers
    const saveKeyBtn = document.getElementById("save-auth-key-btn");
    if (saveKeyBtn) {
      saveKeyBtn.addEventListener("click", () => {
        const newKey = document.getElementById("input-admin-key").value.trim();
        if (newKey) {
          this.adminKey = newKey;
          localStorage.setItem("admin_api_key", newKey);
          this.updateKeyLabel();
          this.closeModal("auth-key-modal");
          this.showToast("Admin API key updated", "success");
          this.fetchAllData();
        }
      });
    }

    const saveLimitBtn = document.getElementById("save-mandate-limit-btn");
    if (saveLimitBtn) saveLimitBtn.addEventListener("click", () => this.handleSaveMandateLimit());

    const createCustBtn = document.getElementById("create-customer-btn");
    if (createCustBtn) createCustBtn.addEventListener("click", () => this.handleCreateCustomer());
  }

  updateKeyLabel() {
    if (this.activeKeyLabel) {
      const masked = this.adminKey.length > 8 ? `${this.adminKey.substring(0, 7)}...` : this.adminKey;
      this.activeKeyLabel.textContent = masked;
    }
  }

  switchTab(tabId) {
    this.currentTab = tabId;
    this.navItems.forEach((item) => {
      item.classList.toggle("active", item.getAttribute("data-tab") === tabId);
    });
    this.tabPanes.forEach((pane) => {
      pane.classList.toggle("active", pane.id === `tab-${tabId}`);
    });
  }

  openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add("active");
  }

  closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove("active");
  }

  startAutoRefresh() {
    this.stopAutoRefresh();
    this.autoRefreshTimer = setInterval(() => {
      if (this.autoRefreshEnabled) {
        this.fetchAllData();
      }
    }, 15000);
  }

  stopAutoRefresh() {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = null;
    }
  }

  async fetchWithAuth(url, options = {}) {
    const headers = {
      "X-Admin-API-Key": this.adminKey,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      this.showToast("Unauthorized: Invalid Admin API Key", "error");
      this.openModal("auth-key-modal");
      throw new Error("Unauthorized");
    }
    return res;
  }

  async fetchAllData() {
    try {
      if (this.refreshIcon) this.refreshIcon.style.transform = "rotate(360deg)";
      await Promise.all([
        this.fetchAuditRecords(),
        this.fetchMandates(),
        this.fetchCatalog(),
      ]);
      this.renderOverviewMetrics();
      this.renderAuditTable();
      this.renderMandatesTable();
      this.renderCatalogGrid();
      if (this.lastSyncedLabel) {
        this.lastSyncedLabel.textContent = `Last synced ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
      }
    } catch (e) {
      console.error("Dashboard fetch error:", e);
    } finally {
      if (this.refreshIcon) {
        setTimeout(() => {
          this.refreshIcon.style.transform = "none";
        }, 400);
      }
    }
  }

  async fetchAuditRecords() {
    try {
      const res = await this.fetchWithAuth("/audit");
      if (res.ok) {
        this.auditRecords = await res.json();
      }
    } catch (e) {
      console.warn("Failed fetching audit:", e);
    }
  }

  async fetchMandates() {
    try {
      const res = await this.fetchWithAuth("/admin/customers");
      if (res.ok) {
        this.mandates = await res.json();
        this.populateCustomerSelect();
      }
    } catch (e) {
      console.warn("Failed fetching mandates:", e);
    }
  }

  async fetchCatalog() {
    try {
      const res = await fetch("/products");
      if (res.ok) {
        this.products = await res.json();
      }
    } catch (e) {
      console.warn("Failed fetching catalog:", e);
    }
  }

  populateCustomerSelect() {
    if (!this.sandboxCustomerSelect || !Array.isArray(this.mandates)) return;
    const currentVal = this.sandboxCustomerSelect.value;
    this.sandboxCustomerSelect.innerHTML = this.mandates
      .map((m) => {
        const lim = (m.max_transaction_amount ?? m.mandate_limit ?? 0).toLocaleString("en-IN");
        return `<option value="${m.customer_id}">${m.customer_id} — ${m.display_name} (₹${lim} limit)</option>`;
      })
      .join("");
    if (currentVal) this.sandboxCustomerSelect.value = currentVal;
  }

  renderOverviewMetrics() {
    const totalTx = this.auditRecords ? this.auditRecords.length : 0;
    const approvedTx = (this.auditRecords || []).filter((r) => r.decision === "APPROVED");
    const totalVolume = approvedTx.reduce((sum, r) => sum + (Number(r.amount) || 0), 0);
    const rate = totalTx > 0 ? Math.round((approvedTx.length / totalTx) * 100) : 0;

    if (this.kpiTotalVolume) this.kpiTotalVolume.textContent = `₹${totalVolume.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
    if (this.kpiApprovedCount) this.kpiApprovedCount.textContent = `${approvedTx.length} approved orders`;
    if (this.kpiTotalTx) this.kpiTotalTx.textContent = totalTx;
    if (this.kpiApprovalRate) this.kpiApprovalRate.textContent = `${rate}%`;
    if (this.kpiProgress) this.kpiProgress.style.width = `${rate}%`;
    if (this.kpiMandateCount) this.kpiMandateCount.textContent = this.mandates ? this.mandates.length : 0;
    if (this.auditCountBadge) this.auditCountBadge.textContent = totalTx;

    // Render recent snippet
    if (this.recentTbody) {
      const recent = (this.auditRecords || []).slice(0, 6);
      if (recent.length === 0) {
        this.recentTbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-muted">No transactions recorded in audit trail yet.</td></tr>`;
        return;
      }
      this.recentTbody.innerHTML = recent
        .map((r) => {
          const product = (this.products || []).find((p) => p.id === r.product_id);
          const pName = escapeHtml(product ? product.name : (r.product_id || "Unknown"));
          const refCode = r.transaction_id ? `REF-${escapeHtml(r.transaction_id.slice(-8).toUpperCase())}` : "—";
          const decBadge =
            r.decision === "APPROVED"
              ? `<span class="badge badge-success">APPROVED</span>`
              : `<span class="badge badge-danger">REJECTED</span>`;
          const payBadge = r.payment_status === "created" || r.payment_status === "captured"
            ? `<span class="badge badge-success">${escapeHtml(r.payment_status)}</span>`
            : r.payment_status === "failed"
            ? `<span class="badge badge-danger">failed</span>`
            : `<span class="badge badge-neutral">${escapeHtml(r.payment_status || "none")}</span>`;
          const amountDisplay = (Number(r.amount) || 0).toFixed(2);
          const timeDisplay = r.timestamp ? escapeHtml(new Date(r.timestamp).toLocaleTimeString()) : "—";
          const safeCustId = escapeHtml(r.customer_id || "—");

          return `
            <tr>
              <td class="mono text-xs">${timeDisplay}</td>
              <td class="mono text-xs font-semibold">${refCode}</td>
              <td><span class="mono text-xs">${safeCustId}</span></td>
              <td>${pName}</td>
              <td class="mono font-semibold">₹${amountDisplay}</td>
              <td>${decBadge}</td>
              <td>${payBadge}</td>
              <td>
                <button class="btn btn-ghost btn-sm" onclick="dashboard.showTxDetail('${escapeHtml(r.transaction_id)}')">Inspect</button>
              </td>
            </tr>
          `;
        })
        .join("");
    }
  }

  renderAuditTable() {
    if (!this.auditTbody) return;
    const query = (this.auditSearch ? this.auditSearch.value : "").trim().toLowerCase();
    const decision = this.auditDecisionFilter ? this.auditDecisionFilter.value : "";
    const customer = this.auditCustomerFilter ? this.auditCustomerFilter.value : "";

    let filtered = (this.auditRecords || []).filter((r) => {
      const product = (this.products || []).find((p) => p.id === r.product_id);
      const pName = (product ? product.name : (r.product_id || "")).toLowerCase();
      const refCode = (r.transaction_id ? r.transaction_id.slice(-8) : "").toLowerCase();
      const custStr = (r.customer_id || "").toLowerCase();
      const fullSearch = `${pName} ${refCode} ${custStr}`;

      if (query && !fullSearch.includes(query)) return false;
      if (decision && r.decision !== decision) return false;
      if (customer && r.customer_id !== customer) return false;
      return true;
    });

    if (filtered.length === 0) {
      this.auditTbody.innerHTML = `<tr><td colspan="9" class="text-center py-6 text-muted">No matching audit records found.</td></tr>`;
      return;
    }

    this.auditTbody.innerHTML = filtered
      .map((r) => {
        const product = (this.products || []).find((p) => p.id === r.product_id);
        const pName = escapeHtml(product ? product.name : (r.product_id || "—"));
        const refCode = r.transaction_id ? `REF-${escapeHtml(r.transaction_id.slice(-8).toUpperCase())}` : "—";
        const decBadge =
          r.decision === "APPROVED"
            ? `<span class="badge badge-success">APPROVED</span>`
            : `<span class="badge badge-danger">REJECTED</span>`;
        const rzpId = r.razorpay_order_id ? `<span class="mono text-xs">${escapeHtml(r.razorpay_order_id)}</span>` : `<span class="text-muted text-xs">—</span>`;
        const timeStr = r.timestamp ? escapeHtml(new Date(r.timestamp).toISOString().replace("T", " ").slice(0, 19)) : "—";
        const amountDisplay = (Number(r.amount) || 0).toFixed(2);
        const safeCustId = escapeHtml(r.customer_id || "—");

        return `
          <tr>
            <td class="mono text-xs">${timeStr}</td>
            <td class="mono text-xs font-semibold">${refCode}</td>
            <td><span class="mono text-xs">${safeCustId}</span></td>
            <td>${pName}</td>
            <td>${escapeHtml(r.quantity || 1)}</td>
            <td class="mono font-semibold">₹${amountDisplay}</td>
            <td>${decBadge}</td>
            <td>${rzpId}</td>
            <td>
              <button class="btn btn-secondary btn-sm" onclick="dashboard.showTxDetail('${escapeHtml(r.transaction_id)}')">View</button>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  renderMandatesTable() {
    if (!this.mandatesTbody) return;
    if (!this.mandates || this.mandates.length === 0) {
      this.mandatesTbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-muted">No mandates configured.</td></tr>`;
      return;
    }

    this.mandatesTbody.innerHTML = this.mandates
      .map((m) => {
        const cats = Array.isArray(m.allowed_categories)
          ? m.allowed_categories.map((c) => `<span class="badge badge-neutral">${escapeHtml(c)}</span>`).join(" ")
          : "—";
        const merches = Array.isArray(m.allowed_merchants)
          ? m.allowed_merchants.map((mech) => `<span class="mono text-xs">${escapeHtml(mech)}</span>`).join(", ")
          : "—";
        const exp = m.expires_at ? escapeHtml(new Date(m.expires_at).toLocaleDateString()) : "Never";
        const rawLimit = Number(m.max_transaction_amount ?? m.mandate_limit) || 0;
        const lim = rawLimit.toLocaleString("en-IN", { minimumFractionDigits: 2 });
        const safeCustId = escapeHtml(m.customer_id);
        const safeName = escapeHtml(m.display_name || "—");
        const safeEmail = escapeHtml(m.email || "—");

        return `
          <tr>
            <td class="mono font-semibold">${safeCustId}</td>
            <td class="font-semibold text-primary">${safeName}</td>
            <td class="text-xs text-muted">${safeEmail}</td>
            <td class="mono font-bold text-success">₹${lim}</td>
            <td>${cats}</td>
            <td>${merches}</td>
            <td class="text-xs text-muted">${exp}</td>
            <td>
              <button class="btn btn-secondary btn-sm" onclick="dashboard.openEditMandateModal('${safeCustId}', '${safeName}', ${rawLimit})">
                Edit Limit
              </button>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  renderCatalogGrid() {
    if (!this.catalogGrid) return;
    if (!this.products || this.products.length === 0) {
      this.catalogGrid.innerHTML = `<div class="text-center py-6 text-muted">Loading catalog...</div>`;
      return;
    }

    this.catalogGrid.innerHTML = this.products
      .map((p) => {
        const stockBadge = p.stock > 10
          ? `<span class="badge badge-success">${p.stock} in stock</span>`
          : p.stock > 0
          ? `<span class="badge badge-warning">${p.stock} left</span>`
          : `<span class="badge badge-danger">Out of stock</span>`;

        const priceDisplay = (Number(p.price) || 0).toLocaleString("en-IN");
        const safeId = escapeHtml(p.id);
        const safeCat = escapeHtml(p.category);
        const safeName = escapeHtml(p.name);
        const safeDesc = escapeHtml(p.description || "No description provided.");

        return `
          <div class="product-card">
            <div>
              <div class="product-card-top">
                <span class="product-id-tag">${safeId}</span>
                <span class="badge badge-neutral">${safeCat}</span>
              </div>
              <h4 class="product-name">${safeName}</h4>
              <p class="product-desc">${safeDesc}</p>
            </div>
            <div class="product-card-bottom">
              <span class="product-price">₹${priceDisplay}</span>
              ${stockBadge}
            </div>
          </div>
        `;
      })
      .join("");
  }

  showTxDetail(txId) {
    const record = (this.auditRecords || []).find((r) => r.transaction_id === txId);
    if (!record) return;
    this.txDetailJson.textContent = JSON.stringify(record, null, 2);
    this.openModal("tx-detail-modal");
  }

  openEditMandateModal(custId, name, currentLimit) {
    document.getElementById("modal-mandate-cust-id").value = custId;
    document.getElementById("modal-mandate-name").value = name;
    document.getElementById("modal-mandate-new-limit").value = currentLimit;
    this.openModal("mandate-modal");
  }

  async handleSaveMandateLimit() {
    const custId = document.getElementById("modal-mandate-cust-id").value;
    const newLimit = parseFloat(document.getElementById("modal-mandate-new-limit").value);

    if (isNaN(newLimit) || newLimit <= 0) {
      this.showToast("Please enter a valid mandate limit > 0", "error");
      return;
    }

    try {
      const res = await this.fetchWithAuth(`/admin/customers/${custId}/mandate`, {
        method: "PATCH",
        body: JSON.stringify({ mandate_limit: newLimit }),
      });

      if (res.ok) {
        this.closeModal("mandate-modal");
        this.showToast(`Mandate limit for ${custId} updated to ₹${newLimit.toFixed(2)}`, "success");
        await this.fetchAllData();
      } else {
        const err = await res.json();
        this.showToast(err.detail || "Failed to update mandate limit", "error");
      }
    } catch (e) {
      this.showToast("Network error updating mandate", "error");
    }
  }

  async handleCreateCustomer() {
    const custId = document.getElementById("new-cust-id").value.trim();
    const name = document.getElementById("new-cust-name").value.trim();
    const email = document.getElementById("new-cust-email").value.trim();
    const password = document.getElementById("new-cust-password").value;
    const limit = parseFloat(document.getElementById("new-cust-limit").value);
    const catsStr = document.getElementById("new-cust-categories").value;
    const merchesStr = document.getElementById("new-cust-merchants").value;

    if (!custId || !name || isNaN(limit)) {
      this.showToast("Please fill in required customer ID, name, and limit", "error");
      return;
    }

    const payload = {
      customer_id: custId,
      display_name: name,
      email: email || undefined,
      password: password || undefined,
      mandate_limit: limit,
      allowed_categories: catsStr.split(",").map((s) => s.trim()).filter(Boolean),
      allowed_merchants: merchesStr.split(",").map((s) => s.trim()).filter(Boolean),
    };

    try {
      const res = await this.fetchWithAuth("/admin/customers", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      if (res.status === 201) {
        this.closeModal("new-customer-modal");
        this.showToast(`Customer ${custId} provisioned successfully!`, "success");
        await this.fetchAllData();
      } else {
        const err = await res.json();
        this.showToast(err.detail || "Failed to create customer", "error");
      }
    } catch (e) {
      this.showToast("Network error provisioning customer", "error");
    }
  }

  async runSandboxInquiry() {
    const prompt = this.sandboxPrompt.value.trim();
    if (!prompt) {
      this.showToast("Please enter a natural language inquiry", "error");
      return;
    }

    this.sandboxStatusPill.className = "badge badge-warning";
    this.sandboxStatusPill.textContent = "Consulting Merchant AI...";
    this.sandboxConsole.innerHTML = `
      <div class="trace-step info">
        <div class="trace-step-header">🤖 Step 1: Buyer AI ➔ Merchant Sales AI</div>
        <div>Inquiry: "${escapeHtml(prompt)}"</div>
        <div class="text-xs text-muted mt-2">Connecting to Google Gemini Merchant Agent...</div>
      </div>
    `;

    try {
      const budget = parseFloat(this.sandboxBudget.value) || null;
      const qty = parseInt(this.sandboxQty.value, 10) || 1;

      const res = await fetch("/merchant/inquire", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: prompt, max_budget: budget, quantity: qty }),
      });

      if (res.ok) {
        const data = await res.json();
        this.sandboxStatusPill.className = "badge badge-success";
        this.sandboxStatusPill.textContent = "Quote Formulated";

        this.sandboxConsole.innerHTML = `
          <div class="trace-step info">
            <div class="trace-step-header">🤖 Step 1: Buyer AI ➔ Merchant Sales AI</div>
            <div>Inquiry: "${escapeHtml(prompt)}"</div>
          </div>
          <div class="trace-step success">
            <div class="trace-step-header">🛍️ Step 2: Merchant Sales AI Quote (Gemini)</div>
            <div class="text-primary font-bold">${escapeHtml(data.merchant_notes)}</div>
            <div class="mt-2 text-xs">Top Match ID: <span class="mono">${escapeHtml(data.best_match_product_id || "None")}</span></div>
            <pre class="json-viewer mt-2">${escapeHtml(JSON.stringify(data.quotes, null, 2))}</pre>
          </div>
        `;
      }
    } catch (e) {
      this.sandboxStatusPill.className = "badge badge-danger";
      this.sandboxStatusPill.textContent = "Error";
      this.sandboxConsole.innerHTML += `<div class="trace-step danger">Error invoking Merchant AI: ${escapeHtml(e.message)}</div>`;
    }
  }

  async runSandboxPurchase() {
    const prompt = this.sandboxPrompt.value.trim();
    if (!prompt) {
      this.showToast("Please enter an inquiry or product", "error");
      return;
    }

    const custId = this.sandboxCustomerSelect.value;
    const qty = parseInt(this.sandboxQty.value, 10) || 1;

    this.sandboxStatusPill.className = "badge badge-warning";
    this.sandboxStatusPill.textContent = "Executing A2A Pipeline...";
    this.sandboxConsole.innerHTML = `
      <div class="trace-step info">
        <div class="trace-step-header">🚀 Initiating Autonomous Agent-to-Agent Flow</div>
        <div>Customer: <span class="mono">${escapeHtml(custId)}</span> | Query: "${escapeHtml(prompt)}"</div>
      </div>
    `;

    try {
      // Step 1: Inquire Merchant AI
      const inqRes = await fetch("/merchant/inquire", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: prompt, quantity: qty }),
      });
      const inqData = await inqRes.json();
      const productId = inqData.best_match_product_id || "KB001";

      // Step 2: Propose Purchase (Authenticated via Admin Key)
      const purRes = await fetch("/agent/purchase", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-API-Key": this.adminKey,
        },
        body: JSON.stringify({
          customer_id: custId,
          product_id: productId,
          quantity: qty,
          idempotency_key: `sandbox-${Date.now()}`,
        }),
      });
      const purData = await purRes.json();

      const isGated = purData.requires_confirmation;

      if (isGated && purData.confirmation_token) {
        this.sandboxStatusPill.className = "badge badge-warning";
        this.sandboxStatusPill.textContent = "Awaiting Human Approval";
        this.sandboxConsole.innerHTML = `
          <div class="trace-step info">
            <div class="trace-step-header">🤖 Step 1: Merchant AI Quote</div>
            <div>Matched Product: <span class="mono font-bold">${escapeHtml(productId)}</span></div>
            <div class="text-xs text-muted">${escapeHtml(inqData.merchant_notes)}</div>
          </div>
          <div class="trace-step warning">
            <div class="trace-step-header">🛡️ Step 2: Policy Mandate Evaluation (Gated: >= ₹500)</div>
            <div class="font-bold text-warning">Status: ${escapeHtml(purData.decision)}</div>
            <div class="text-sm mt-1">${escapeHtml(purData.reason)}</div>
            <div class="mt-2 text-xs text-muted">Confirmation Token Minted: <span class="mono">${escapeHtml(purData.confirmation_token.slice(0, 28))}...</span></div>
          </div>
          <div class="trace-step" style="border: 2px solid #f59e0b; background: rgba(245, 158, 11, 0.08); border-radius: 8px; padding: 16px;">
            <div class="trace-step-header" style="font-size: 14px; font-weight: 700; color: #f59e0b;">
              👤 Human Approval Challenge
            </div>
            <div class="text-sm mt-1">
              Safety Gating Rule: Purchases <strong>≥ ₹500.00</strong> require explicit human authorization before funds movement.
            </div>
            <div class="mt-3 p-3" style="background: rgba(0,0,0,0.25); border-radius: 6px; font-size: 13px;">
              <div><strong>Product:</strong> ${escapeHtml(productId)} (Quantity: ${qty})</div>
              <div><strong>Total Transaction Value:</strong> <span class="mono font-bold" style="color: #10b981;">₹${(Number(purData.amount) || 0).toFixed(2)}</span></div>
              <div><strong>Mandate Limit:</strong> ₹${(Number(purData.mandate_limit) || 0).toFixed(2)}</div>
            </div>
            <div style="display: flex; gap: 12px; margin-top: 16px;">
              <button id="sandbox-btn-approve" class="btn btn-primary" style="flex: 1; background: #10b981; border: none; font-weight: 600; padding: 10px;">
                ✅ Approve & Mint Razorpay Order
              </button>
              <button id="sandbox-btn-reject" class="btn btn-secondary" style="flex: 1; background: #ef4444; border: none; color: white; font-weight: 600; padding: 10px;">
                ❌ Reject Proposal
              </button>
            </div>
          </div>
        `;

        // Attach Interactive Click Handlers for Human in the Loop
        document.getElementById("sandbox-btn-approve").addEventListener("click", async () => {
          await this.executeHumanConfirmation(purData.confirmation_token, productId, inqData, purData.amount);
        });

        document.getElementById("sandbox-btn-reject").addEventListener("click", () => {
          this.executeHumanRejection(productId, inqData, purData.amount);
        });

        await this.fetchAllData();
        return;
      }

      // Non-gated flow (< ₹500 micro-purchases or direct rejections)
      this.renderPurchaseCompletion(purData, productId, inqData);
    } catch (e) {
      this.sandboxStatusPill.className = "badge badge-danger";
      this.sandboxStatusPill.textContent = "Execution Failed";
      this.sandboxConsole.innerHTML += `<div class="trace-step danger">Execution Error: ${escapeHtml(e.message)}</div>`;
    }
  }

  async executeHumanConfirmation(token, productId, inqData, amount) {
    this.sandboxStatusPill.className = "badge badge-warning";
    this.sandboxStatusPill.textContent = "Processing Payment Rails...";
    try {
      const confRes = await fetch("/agent/confirm", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-API-Key": this.adminKey,
        },
        body: JSON.stringify({ confirmation_token: token }),
      });
      const confData = await confRes.json();
      this.renderPurchaseCompletion(confData, productId, inqData, true);
    } catch (err) {
      this.sandboxStatusPill.className = "badge badge-danger";
      this.sandboxStatusPill.textContent = "Confirmation Failed";
      this.showToast(`Confirmation failed: ${err.message}`, "error");
    }
  }

  executeHumanRejection(productId, inqData, amount) {
    this.sandboxStatusPill.className = "badge badge-danger";
    this.sandboxStatusPill.textContent = "Rejected by Human";
    this.sandboxConsole.innerHTML = `
      <div class="trace-step info">
        <div class="trace-step-header">🤖 Step 1: Merchant AI Quote</div>
        <div>Matched Product: <span class="mono font-bold">${escapeHtml(productId)}</span></div>
        <div class="text-xs text-muted">${escapeHtml(inqData.merchant_notes)}</div>
      </div>
      <div class="trace-step danger">
        <div class="trace-step-header">❌ Human Decision</div>
        <div class="font-bold">Proposal explicitly rejected by customer.</div>
        <div class="text-xs mt-1">Payment rails halted. No Razorpay order minted. Zero funds spent.</div>
      </div>
    `;
    this.showToast("Proposal was cancelled by human operator", "info");
  }

  renderPurchaseCompletion(purData, productId, inqData, humanConfirmed = false) {
    const isApproved = purData.decision === "APPROVED";
    this.sandboxStatusPill.className = isApproved ? "badge badge-success" : "badge badge-danger";
    this.sandboxStatusPill.textContent = isApproved ? "Purchase Approved" : "Policy Rejected";

    const refCode = isApproved ? `REF-${purData.transaction_id.slice(-8).toUpperCase()}` : "N/A";
    const rzpOrderId = purData.payment && purData.payment.razorpay_order_id
      ? `<span class="mono font-bold text-success">${escapeHtml(purData.payment.razorpay_order_id)}</span>`
      : "None (Policy Rejected)";

    const humanTag = humanConfirmed
      ? `<div class="badge badge-success mb-2">✓ Verified via Human Confirmation Challenge</div>`
      : "";

    this.sandboxConsole.innerHTML = `
      <div class="trace-step info">
        <div class="trace-step-header">🤖 Step 1: Merchant AI Quote</div>
        <div>Matched Product: <span class="mono font-bold">${escapeHtml(productId)}</span></div>
        <div class="text-xs text-muted">${escapeHtml(inqData.merchant_notes)}</div>
      </div>
      <div class="trace-step ${isApproved ? "success" : "danger"}">
        ${humanTag}
        <div class="trace-step-header">🛡️ Step 2: Policy & Payment Rails Outcome</div>
        <div class="font-bold">Verdict: ${escapeHtml(purData.decision)}</div>
        <div>Reason: ${escapeHtml(purData.reason)}</div>
        <div class="mt-2 text-xs">Total Amount: <span class="mono font-bold">₹${(Number(purData.amount) || 0).toFixed(2)}</span></div>
        <div class="text-xs">Razorpay Order ID: ${rzpOrderId}</div>
        <div class="text-xs">Human Reference Code: <span class="mono font-bold">${escapeHtml(refCode)}</span></div>
      </div>
    `;

    this.fetchAllData();
    this.showToast(`Sandbox run completed: ${purData.decision}`, isApproved ? "success" : "error");
  }


  showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${type === "success" ? "✓" : type === "error" ? "⚠" : "ℹ"}</span> <span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 200);
    }, 3000);
  }
}

// Instantiate dashboard globally
let dashboard;
document.addEventListener("DOMContentLoaded", () => {
  dashboard = new AdminDashboard();
});
