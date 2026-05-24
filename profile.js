const authPanel = document.querySelector("#auth-panel");
const authForm = document.querySelector("#auth-form");
const authStatus = document.querySelector("#auth-status");
const botLink = document.querySelector("#bot-link");
const profileView = document.querySelector("#profile-view");
const profileName = document.querySelector("#profile-name");
const profileFacts = document.querySelector("#profile-facts");
const ordersList = document.querySelector("#orders-list");
const logoutButton = document.querySelector("#logout-button");
const adminView = document.querySelector("#admin-view");
const adminOrdersList = document.querySelector("#admin-orders-list");
const customersList = document.querySelector("#customers-list");
const statusFilter = document.querySelector("#status-filter");
const fallbackBotLoginUrl = "https://t.me/rag_pack_bot?start=login";

let statuses = {};

const statusText = (statusMap, status) => statusMap?.[status] || status;

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

const setAuthStatus = (message, type = "") => {
  authStatus.textContent = message;
  authStatus.dataset.type = type;
};

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

const renderProfileOrders = (orders, statusMap) => {
  if (!orders.length) {
    ordersList.innerHTML = '<p class="empty-state">Заказов пока нет.</p>';
    return;
  }

  ordersList.innerHTML = orders
    .map(
      (order) => `
        <article class="table-row">
          <div>
            <strong>#${order.id} / ${escapeHtml(order.product_name)}</strong>
            <span>${escapeHtml(order.product_price)} / ${escapeHtml(order.created_at)}</span>
          </div>
          <div>
            <span class="status-pill">${escapeHtml(statusText(statusMap, order.status))}</span>
            <span>${escapeHtml(order.delivery_address)}</span>
          </div>
        </article>
      `,
    )
    .join("");
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

const renderAdminOrders = (orders) => {
  if (!orders.length) {
    adminOrdersList.innerHTML = '<p class="empty-state">Заказов нет.</p>';
    return;
  }

  adminOrdersList.innerHTML = orders
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

const loadAdminOrders = async () => {
  const query = statusFilter.value ? `?status=${encodeURIComponent(statusFilter.value)}` : "";
  const payload = await api(`/api/admin/orders${query}`, { headers: {} });
  statuses = payload.statuses;
  renderStatusOptions();
  renderAdminOrders(payload.orders);
};

const loadCustomers = async () => {
  const payload = await api("/api/admin/customers", { headers: {} });
  renderCustomers(payload.customers);
};

const loadAdmin = async () => {
  await loadAdminOrders();
  await loadCustomers();
  adminView.hidden = false;
};

const renderProfile = async (payload) => {
  const { user, orders, statuses: profileStatuses } = payload;
  const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ") || "Профиль клиента";

  profileName.textContent = displayName;
  profileFacts.innerHTML = `
    <div><dt>Телефон</dt><dd>${escapeHtml(user.phone || "не указан")}</dd></div>
    <div><dt>Telegram</dt><dd>${escapeHtml(user.telegram_username ? `@${user.telegram_username}` : user.telegram_user_id)}</dd></div>
    <div><dt>Права</dt><dd>${user.is_admin ? "Админ" : "Пользователь"}</dd></div>
  `;
  renderProfileOrders(orders, profileStatuses);
  authPanel.hidden = true;
  profileView.hidden = false;
  adminView.hidden = true;

  if (user.is_admin) {
    await loadAdmin();
  }
};

const loadProfile = async () => {
  try {
    const payload = await api("/api/profile", { headers: {} });
    await renderProfile(payload);
  } catch (error) {
    authPanel.hidden = false;
    profileView.hidden = true;
    adminView.hidden = true;
  }
};

const loadBotLink = async () => {
  botLink.href = fallbackBotLoginUrl;

  try {
    const payload = await api("/api/auth/start", { method: "POST" });
    botLink.href = payload.login_url || fallbackBotLoginUrl;
  } catch (error) {
    setAuthStatus("");
  }
};

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(authForm);
  const code = formData.get("code")?.trim();

  setAuthStatus("Проверяем код...");
  authForm.querySelector("button").disabled = true;

  try {
    await api("/api/auth/verify", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    authForm.reset();
    setAuthStatus("");
    await loadProfile();
  } catch (error) {
    setAuthStatus("Код не подошел или уже истек.", "error");
  } finally {
    authForm.querySelector("button").disabled = false;
  }
});

adminOrdersList.addEventListener("change", async (event) => {
  const select = event.target.closest("[data-order-status]");
  if (!select) {
    return;
  }

  await api(`/api/admin/orders/${select.dataset.orderStatus}`, {
    method: "PATCH",
    body: JSON.stringify({ status: select.value }),
  });
  await loadAdminOrders();
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

statusFilter.addEventListener("change", loadAdminOrders);

logoutButton.addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" }).catch(() => ({}));
  await loadProfile();
});

loadBotLink();
loadProfile();
