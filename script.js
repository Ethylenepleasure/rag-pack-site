const productGrid = document.querySelector("#product-grid");
const dialog = document.querySelector("#order");
const orderForm = document.querySelector("#order-form");
const selectedProduct = document.querySelector("#selected-product");
const orderStatus = document.querySelector("#order-status");
const closeButton = document.querySelector(".order-form__close");
const apiUrl = document.querySelector('meta[name="ragpack-api-url"]')?.content || "/api/orders";

let selectedProductData = null;

const escapeHtml = (value) =>
  String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    };

    return entities[char];
  });

const setStatus = (message, type = "") => {
  orderStatus.textContent = message;
  orderStatus.dataset.type = type;
};

const openOrderDialog = (product) => {
  selectedProductData = product;
  selectedProduct.textContent = `${product.name} / ${product.price}`;
  setStatus("");
  orderForm.reset();

  if (typeof dialog.showModal === "function") {
    dialog.showModal();
    return;
  }

  window.location.hash = "order";
};

const createProductCard = (product) => {
  const card = document.createElement("article");
  card.className = "product-card";
  card.innerHTML = `
    <div class="product-card__image">
      <img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.alt)}" />
    </div>
    <div class="product-card__body">
      <span class="product-card__tag">${escapeHtml(product.tag)}</span>
      <h3>${escapeHtml(product.name)}</h3>
      <p>${escapeHtml(product.description)}</p>
      <div class="product-card__bottom">
        <strong>${escapeHtml(product.price)}</strong>
        <button type="button">Заказать</button>
      </div>
    </div>
  `;

  card.querySelector("button").addEventListener("click", () => openOrderDialog(product));
  return card;
};

const loadCatalog = async () => {
  try {
    const response = await fetch("catalog.json", { cache: "no-store" });

    if (!response.ok) {
      throw new Error("catalog request failed");
    }

    const products = await response.json();
    productGrid.replaceChildren(...products.map(createProductCard));
  } catch (error) {
    productGrid.innerHTML = `
      <p class="catalog__fallback">
        Каталог временно не загрузился. Напишите креэйтору в Telegram:
        <a href="https://t.me/ragpackleather">https://t.me/ragpackleather</a>
      </p>
    `;
  }
};

closeButton.addEventListener("click", () => {
  if (typeof dialog.close === "function") {
    dialog.close();
  }
});

orderForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!selectedProductData) {
    setStatus("Выберите товар из каталога.", "error");
    return;
  }

  const formData = new FormData(orderForm);

  if (formData.get("company")) {
    return;
  }

  const payload = {
    product_slug: selectedProductData.slug,
    customer_name: formData.get("customer_name")?.trim(),
    delivery_address: formData.get("delivery_address")?.trim(),
    telegram_contact: formData.get("telegram_contact")?.trim(),
  };

  setStatus("Отправляем заявку...");
  orderForm.querySelector(".order-form__submit").disabled = true;

  try {
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(result.detail || "order request failed");
    }

    setStatus("Спасибо за заказ! Наш менеджер скоро напишет вам по поводу оплаты.", "success");
    orderForm.reset();
  } catch (error) {
    setStatus("Не получилось отправить заявку. Проверьте поля или напишите креэйтору в Telegram.", "error");
  } finally {
    orderForm.querySelector(".order-form__submit").disabled = false;
  }
});

loadCatalog();
