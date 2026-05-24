const authPanel = document.querySelector("#auth-panel");
const authForm = document.querySelector("#auth-form");
const authStatus = document.querySelector("#auth-status");
const botLink = document.querySelector("#bot-link");
const profileView = document.querySelector("#profile-view");
const profileName = document.querySelector("#profile-name");
const profileFacts = document.querySelector("#profile-facts");
const ordersList = document.querySelector("#orders-list");
const logoutButton = document.querySelector("#logout-button");
const fallbackBotLoginUrl = "https://t.me/rag_pack_bot?start=login";

const statusText = (statuses, status) => statuses?.[status] || status;

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

const renderOrders = (orders, statuses) => {
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
            <span class="status-pill">${escapeHtml(statusText(statuses, order.status))}</span>
            <span>${escapeHtml(order.delivery_address)}</span>
          </div>
        </article>
      `,
    )
    .join("");
};

const renderProfile = (payload) => {
  const { user, orders, statuses } = payload;
  const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ") || "Профиль клиента";

  profileName.textContent = displayName;
  profileFacts.innerHTML = `
    <div><dt>Телефон</dt><dd>${escapeHtml(user.phone || "не указан")}</dd></div>
    <div><dt>Telegram</dt><dd>${escapeHtml(user.telegram_username ? `@${user.telegram_username}` : user.telegram_user_id)}</dd></div>
    <div><dt>Статус</dt><dd>${user.is_admin ? "Админ" : "Клиент"}</dd></div>
  `;
  renderOrders(orders, statuses);
  authPanel.hidden = true;
  profileView.hidden = false;
};

const loadProfile = async () => {
  try {
    const payload = await api("/api/profile", { headers: {} });
    renderProfile(payload);
  } catch (error) {
    authPanel.hidden = false;
    profileView.hidden = true;
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

logoutButton.addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" }).catch(() => ({}));
  await loadProfile();
});

loadBotLink();
loadProfile();
