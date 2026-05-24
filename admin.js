const adminAuthPanel = document.querySelector("#admin-auth-panel");
const adminAuthForm = document.querySelector("#admin-auth-form");
const adminAuthStatus = document.querySelector("#admin-auth-status");
const adminBotLink = document.querySelector("#admin-bot-link");
const adminView = document.querySelector("#admin-view");
const adminLogoutButton = document.querySelector("#admin-logout-button");
const ordersList = document.querySelector("#admin-orders-list");
const customersList = document.querySelector("#customers-list");
const statusFilter = document.querySelector("#status-filter");

let statuses = {};

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };

    return entities[char];
  });

const api = async (url, options = {}) => {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.detail || "request failed");
  }

  return payload;
};

const setAdminAuthStatus = (message, type = "") => {
  adminAuthStatus.textContent = message;
  adminAuthStatus.dataset.type = type;
};

const renderStatusOptions = () => {
  const current = statusFilter.value;
  statusFilter.innerHTML =
    '<option value="">Все статусы</option>' +
    Object.entries(statuses)
      .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`)
      .join("");
  statusFilter.value = current;
};

const renderOrders = (orders) => {
  if (!orders.length) {
    ordersList.innerHTML = '<p class="empty-state">Заказов нет.</p>';
    return;
  }

  ordersList.innerHTML = orders
    .map(
      (order) => `
        <article class="table-row table-row--admin">
          <div>
            <strong>#${order.id} / ${escapeHtml(order.product_name)}</strong>
            <span>${escapeHtml(order.customer_name)} / ${escapeHtml(order.telegram_contact)}</span>
            <span>${escapeHtml(order.delivery_address)}</span>
          </div>
          <div>
            <select data-order-status="${order.id}" aria-label="Статус заказа #${order.id}">
              ${Object.entries(statuses)
                .map(
                  ([value, label]) =>
                    `<option value="${escapeHtml(value)}" ${value === order.status ? "selected" : ""}>${escapeHtml(label)}</option>`,
                )
                .join("")}
            </select>
            <span>${escapeHtml(order.product_price)} / ${escapeHtml(order.created_at)}</span>
          </div>
        </article>
      `,
    )
    .join("");
};

const renderCustomers = (customers) => {
  if (!customers.length) {
    customersList.innerHTML = '<p class="empty-state">Клиентов пока нет.</p>';
    return;
  }

  customersList.innerHTML = customers
    .map(({ user, note, orders_count: ordersCount, last_order: lastOrder }) => {
      const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || `Telegram ${user.telegram_user_id}`;
      return `
        <article class="customer-row">
          <div class="customer-row__head">
            <div>
              <strong>${escapeHtml(name)}</strong>
              <span>${escapeHtml(user.phone || "телефон не указан")} / ${escapeHtml(user.telegram_username ? `@${user.telegram_username}` : user.telegram_user_id)}</span>
            </div>
            <span class="status-pill">${ordersCount} заказ(ов)</span>
          </div>
          <p>${lastOrder ? `Последний: #${lastOrder.id} / ${escapeHtml(lastOrder.product_name)}` : "Заказов пока нет"}</p>
          <label>
            Заметка
            <textarea data-customer-note="${user.id}" rows="3">${escapeHtml(note)}</textarea>
          </label>
          <button class="text-button" type="button" data-save-note="${user.id}">Сохранить заметку</button>
        </article>
      `;
    })
    .join("");
};

const loadOrders = async () => {
  const query = statusFilter.value ? `?status=${encodeURIComponent(statusFilter.value)}` : "";
  const payload = await api(`/api/admin/orders${query}`, { headers: {} });
  statuses = payload.statuses;
  renderStatusOptions();
  renderOrders(payload.orders);
};

const loadCustomers = async () => {
  const payload = await api("/api/admin/customers", { headers: {} });
  renderCustomers(payload.customers);
};

const loadAdmin = async ({ silent = true } = {}) => {
  try {
    await loadOrders();
    await loadCustomers();
    adminAuthPanel.hidden = true;
    adminView.hidden = false;
  } catch (error) {
    adminAuthPanel.hidden = false;
    adminView.hidden = true;
    if (!silent) {
      throw error;
    }
  }
};

const loadBotLink = async () => {
  try {
    const payload = await api("/api/auth/start", { method: "POST" });
    adminBotLink.href = payload.login_url;
  } catch (error) {
    setAdminAuthStatus("Не удалось получить ссылку на бота. Попробуйте обновить страницу.", "error");
  }
};

adminAuthForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(adminAuthForm);
  const code = formData.get("code")?.trim();

  setAdminAuthStatus("Проверяем код...");
  adminAuthForm.querySelector("button").disabled = true;

  try {
    await api("/api/auth/verify", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    adminAuthForm.reset();
    setAdminAuthStatus("");
    await loadAdmin({ silent: false });
  } catch (error) {
    setAdminAuthStatus("Код не подошел, истек или у аккаунта нет доступа.", "error");
  } finally {
    adminAuthForm.querySelector("button").disabled = false;
  }
});

ordersList.addEventListener("change", async (event) => {
  const select = event.target.closest("[data-order-status]");
  if (!select) {
    return;
  }

  await api(`/api/admin/orders/${select.dataset.orderStatus}`, {
    method: "PATCH",
    body: JSON.stringify({ status: select.value }),
  });
  await loadOrders();
});

customersList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-save-note]");
  if (!button) {
    return;
  }

  const customerId = button.dataset.saveNote;
  const textarea = customersList.querySelector(`[data-customer-note="${customerId}"]`);
  button.disabled = true;
  await api(`/api/admin/customers/${customerId}/note`, {
    method: "PATCH",
    body: JSON.stringify({ note: textarea.value }),
  });
  button.disabled = false;
});

statusFilter.addEventListener("change", loadOrders);

adminLogoutButton.addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" }).catch(() => ({}));
  await loadAdmin();
});

loadBotLink();
loadAdmin();
