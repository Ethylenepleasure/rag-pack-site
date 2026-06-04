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
const productsList = document.querySelector("#products-list");
const productForm = document.querySelector("#product-form");
const newProductButton = document.querySelector("#new-product-button");
const productFormStatus = document.querySelector("#product-form-status");
const fallbackBotLoginUrl = "https://t.me/rag_pack_bot?start=login";

let statuses = {};
let products = [];

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

const uploadFile = async (file) => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/admin/uploads", {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.detail || "upload failed");
  }

  return payload.path;
};

const setProductStatus = (message, type = "") => {
  productFormStatus.textContent = message;
  productFormStatus.dataset.type = type;
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

const productStatusLabel = (product) => {
  if (product.is_archived) {
    return "Архив";
  }

  return product.is_published ? "Опубликован" : "Черновик";
};

const renderProducts = () => {
  if (!products.length) {
    productsList.innerHTML = '<p class="empty-state">Товаров пока нет.</p>';
    return;
  }

  productsList.innerHTML = products
    .map(
      (product) => `
        <article class="table-row table-row--admin">
          <div>
            <strong>${escapeHtml(product.name)} / ${escapeHtml(product.price)}</strong>
            <span>${escapeHtml(product.slug)} / ${escapeHtml(product.category)} / ${escapeHtml(product.tag)}</span>
            <span class="status-pill">${escapeHtml(productStatusLabel(product))}</span>
          </div>
          <div class="product-actions">
            <button class="text-button" type="button" data-edit-product="${escapeHtml(product.slug)}">Редактировать</button>
            ${
              product.is_archived
                ? `<button class="text-button" type="button" data-restore-product="${escapeHtml(product.slug)}">Восстановить</button>`
                : `<button class="text-button" type="button" data-archive-product="${escapeHtml(product.slug)}">Убрать из каталога</button>`
            }
          </div>
        </article>
      `,
    )
    .join("");
};

const productToGalleryText = (product) =>
  (product.gallery || []).map((item) => `${item.image}${item.alt ? ` | ${item.alt}` : ""}`).join("\n");

const productToSpecsText = (product) =>
  Object.entries(product.specs || {})
    .map(([label, value]) => `${label} | ${value}`)
    .join("\n");

const productToFeaturesText = (product) => (product.features || []).join("\n");

const fillProductForm = (product = null) => {
  productForm.reset();
  setProductStatus("");

  const data =
    product ||
    {
      slug: "",
      category: "bags",
      tag: "",
      name: "",
      description: "",
      detail_description: "",
      price: "",
      image: "",
      alt: "",
      display_name: "",
      image_fit: "cover",
      title_mark: "",
      title_size: "",
      notes: "",
      is_published: false,
      is_archived: false,
      gallery: [],
      specs: {},
      features: [],
    };

  productForm.elements.original_slug.value = product ? product.slug : "";
  productForm.elements.slug.value = data.slug || "";
  productForm.elements.category.value = data.category || "bags";
  productForm.elements.tag.value = data.tag || "";
  productForm.elements.name.value = data.name || "";
  productForm.elements.description.value = data.description || "";
  productForm.elements.detail_description.value = data.detail_description || "";
  productForm.elements.price.value = data.price || "";
  productForm.elements.image.value = data.image || "";
  productForm.elements.alt.value = data.alt || "";
  productForm.elements.display_name.value = data.display_name || "";
  productForm.elements.image_fit.value = data.image_fit || "cover";
  productForm.elements.title_mark.value = data.title_mark || "";
  productForm.elements.title_size.value = data.title_size || "";
  productForm.elements.notes.value = data.notes || "";
  productForm.elements.is_published.checked = Boolean(data.is_published);
  productForm.elements.gallery_text.value = productToGalleryText(data);
  productForm.elements.specs_text.value = productToSpecsText(data);
  productForm.elements.features_text.value = productToFeaturesText(data);
};

const parseGalleryText = (value) =>
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [image, ...altParts] = line.split("|");
      return { image: image.trim(), alt: altParts.join("|").trim() };
    })
    .filter((item) => item.image);

const parseSpecsText = (value) =>
  Object.fromEntries(
    value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [label, ...valueParts] = line.split("|");
        return [label.trim(), valueParts.join("|").trim()];
      })
      .filter(([label, text]) => label && text),
  );

const parseFeaturesText = (value) =>
  value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

const productPayloadFromForm = () => {
  const formData = new FormData(productForm);
  const originalSlug = formData.get("original_slug")?.trim();
  const existingProduct = products.find((item) => item.slug === originalSlug);
  return {
    slug: formData.get("slug")?.trim(),
    category: formData.get("category")?.trim(),
    tag: formData.get("tag")?.trim(),
    name: formData.get("name")?.trim(),
    description: formData.get("description")?.trim(),
    detail_description: formData.get("detail_description")?.trim(),
    price: formData.get("price")?.trim(),
    image: formData.get("image")?.trim(),
    alt: formData.get("alt")?.trim(),
    display_name: formData.get("display_name")?.trim(),
    image_fit: formData.get("image_fit")?.trim(),
    title_mark: formData.get("title_mark")?.trim(),
    title_size: formData.get("title_size")?.trim(),
    gallery: parseGalleryText(formData.get("gallery_text") || ""),
    specs: parseSpecsText(formData.get("specs_text") || ""),
    features: parseFeaturesText(formData.get("features_text") || ""),
    notes: formData.get("notes")?.trim(),
    is_published: productForm.elements.is_published.checked,
    is_archived: Boolean(existingProduct?.is_archived),
  };
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

const loadProducts = async () => {
  const payload = await api("/api/admin/products", { headers: {} });
  products = payload.products || [];
  renderProducts();
};

const loadAdmin = async () => {
  await loadAdminOrders();
  await loadCustomers();
  await loadProducts();
  fillProductForm();
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

  if (window.location.hash === "#profile-orders") {
    document.querySelector("#profile-orders")?.scrollIntoView();
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

newProductButton.addEventListener("click", () => {
  fillProductForm();
  productForm.scrollIntoView({ behavior: "smooth", block: "start" });
});

productsList.addEventListener("click", async (event) => {
  const editButton = event.target.closest("[data-edit-product]");
  const archiveButton = event.target.closest("[data-archive-product]");
  const restoreButton = event.target.closest("[data-restore-product]");

  if (editButton) {
    const product = products.find((item) => item.slug === editButton.dataset.editProduct);
    if (product) {
      fillProductForm(product);
      productForm.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    return;
  }

  if (archiveButton) {
    const slug = archiveButton.dataset.archiveProduct;
    if (!window.confirm("Убрать товар из каталога сайта и бота?")) {
      return;
    }

    archiveButton.disabled = true;
    await api(`/api/admin/products/${encodeURIComponent(slug)}`, { method: "DELETE" });
    await loadProducts();
    return;
  }

  if (restoreButton) {
    const slug = restoreButton.dataset.restoreProduct;
    const product = products.find((item) => item.slug === slug);
    if (!product) {
      return;
    }

    restoreButton.disabled = true;
    await api(`/api/admin/products/${encodeURIComponent(slug)}`, {
      method: "PATCH",
      body: JSON.stringify({ ...product, is_archived: false, is_published: false }),
    });
    await loadProducts();
  }
});

productForm.elements.main_upload.addEventListener("change", async () => {
  const file = productForm.elements.main_upload.files?.[0];
  if (!file) {
    return;
  }

  setProductStatus("Загружаем основное фото...");
  try {
    productForm.elements.image.value = await uploadFile(file);
    setProductStatus("Фото загружено.", "success");
  } catch (error) {
    setProductStatus("Не получилось загрузить фото.", "error");
  } finally {
    productForm.elements.main_upload.value = "";
  }
});

productForm.elements.gallery_upload.addEventListener("change", async () => {
  const files = Array.from(productForm.elements.gallery_upload.files || []);
  if (!files.length) {
    return;
  }

  setProductStatus("Загружаем фото галереи...");
  try {
    const uploaded = [];
    for (const file of files) {
      uploaded.push(await uploadFile(file));
    }
    const current = productForm.elements.gallery_text.value.trim();
    productForm.elements.gallery_text.value = [current, ...uploaded].filter(Boolean).join("\n");
    setProductStatus("Фото галереи загружены.", "success");
  } catch (error) {
    setProductStatus("Не получилось загрузить фото галереи.", "error");
  } finally {
    productForm.elements.gallery_upload.value = "";
  }
});

productForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submitButton = productForm.querySelector('button[type="submit"]');
  const originalSlug = productForm.elements.original_slug.value;
  const payload = productPayloadFromForm();
  const url = originalSlug ? `/api/admin/products/${encodeURIComponent(originalSlug)}` : "/api/admin/products";
  const method = originalSlug ? "PATCH" : "POST";

  setProductStatus("Сохраняем товар...");
  submitButton.disabled = true;

  try {
    const response = await api(url, {
      method,
      body: JSON.stringify(payload),
    });
    setProductStatus("Товар сохранен.", "success");
    await loadProducts();
    fillProductForm(response.product);
  } catch (error) {
    setProductStatus("Не получилось сохранить товар. Проверьте обязательные поля и slug.", "error");
  } finally {
    submitButton.disabled = false;
  }
});

statusFilter.addEventListener("change", loadAdminOrders);

logoutButton.addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" }).catch(() => ({}));
  await loadProfile();
});

loadBotLink();
loadProfile();
