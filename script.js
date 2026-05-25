const productGrid = document.querySelector("#product-grid");
const dialog = document.querySelector("#order");
const orderForm = document.querySelector("#order-form");
const selectedProduct = document.querySelector("#selected-product");
const orderStatus = document.querySelector("#order-status");
const closeButton = document.querySelector(".order-form__close");
const telegramContactField = document.querySelector("#telegram-contact-field");
const telegramContactInput = orderForm.querySelector('[name="telegram_contact"]');
const profileTelegramContact = document.querySelector("#profile-telegram-contact");
const profileLink = document.querySelector("#profile-link");
const ordersLink = document.querySelector("#orders-link");
const apiUrl = document.querySelector('meta[name="ragpack-api-url"]')?.content || "/api/orders";
const apiBaseUrl = new URL(apiUrl, window.location.href);
const profileUrl = new URL("/profile", apiBaseUrl);
const profileApiUrl = new URL("/api/profile", apiBaseUrl).toString();

let selectedProductData = null;
let currentUser = null;

const fallbackProducts = [
  {
    slug: "bigbulya",
    category: "bags",
    tag: "Дорожная сумка",
    name: "Бигбуля",
    description: "Объемная черная кожа, латунная фурнитура, тяжелый силуэт.",
    price: "22 900 ₽",
    image: "assets/product-2.jpg",
    alt: "Большая черная кожаная сумка с металлической фурнитурой",
  },
  {
    slug: "pitch",
    category: "accessories",
    tag: "Галстук",
    name: "PITCH",
    description: "Рельефная фактура, вытянутый силуэт, акцент для сумки или образа.",
    price: "4 500 ₽",
    image: "assets/knockout-2.jpg",
    alt: "Черный фактурный аксессуар на воротнике",
  },
  {
    slug: "void-carrier",
    category: "bags",
    tag: "Сумка",
    name: "Void Carrier",
    description: "Компактная форма, острые края отделки и мягкий плечевой ремень.",
    price: "12 600 ₽",
    image: "assets/product-4.jpg",
    alt: "Маленькая черная кожаная сумка с длинным ремнем",
  },
  {
    slug: "larva",
    category: "bags",
    tag: "Сумка",
    name: "Larva",
    description: "Полумесяц из гладкой кожи с декоративными боковыми наплывами.",
    price: "14 200 ₽",
    image: "assets/product-5.jpg",
    alt: "Черная полукруглая кожаная сумка на ремне",
  },
  {
    slug: "macbook-15-case",
    category: "cases",
    tag: "Комплект",
    name: "MacBook 15 Case",
    description: "Плоский клатч с мрачной пластичной отделкой и перчаткой.",
    price: "16 800 ₽",
    image: "assets/macbook-15-case-new.jpg",
    alt: "Черный кожаный чехол MacBook 15 Case и перчатка",
  },
  {
    slug: "pod-shell",
    category: "cases",
    tag: "Чехол Air Pods",
    name: "POD SHELL",
    description: "Строгая геометрия, пепельные мазки и драматичный нижний край.",
    price: "1 800 ₽",
    image: "assets/IMG_4168.heic.png",
    alt: "POD SHELL в прозрачной емкости",
  },
];

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

const formatTelegramContact = (user) => {
  if (!user) {
    return "";
  }

  return user.telegram_username ? `@${user.telegram_username}` : String(user.telegram_user_id || "");
};

const applyProfileToOrderForm = () => {
  const telegramContact = formatTelegramContact(currentUser);

  telegramContactField.hidden = Boolean(telegramContact);
  telegramContactInput.required = !telegramContact;
  telegramContactInput.value = telegramContact;
  profileTelegramContact.hidden = !telegramContact;
  profileTelegramContact.textContent = telegramContact ? `Telegram: ${telegramContact}` : "";
};

const applyProfileLinks = () => {
  const profileHref = profileUrl.toString();
  const ordersHref = new URL(profileUrl);
  ordersHref.hash = currentUser ? "profile-orders" : "auth-panel";

  profileLink.href = profileHref;
  ordersLink.href = ordersHref.toString();
};

const loadCurrentUser = async () => {
  try {
    const response = await fetch(profileApiUrl, {
      credentials: "include",
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("profile request failed");
    }

    const payload = await response.json();
    currentUser = payload.user || null;
  } catch (error) {
    currentUser = null;
  }

  applyProfileToOrderForm();
  applyProfileLinks();
};

const openOrderDialog = (product) => {
  selectedProductData = product;
  selectedProduct.textContent = `${product.name} / ${product.price}`;
  setStatus("");
  orderForm.reset();
  applyProfileToOrderForm();

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
  let products = fallbackProducts;

  try {
    const response = await fetch("catalog.json", { cache: "no-store" });

    if (!response.ok) {
      throw new Error("catalog request failed");
    }

    products = await response.json();
  } catch (error) {
    console.warn("Using embedded catalog fallback.", error);
  }

  productGrid.replaceChildren(...products.map(createProductCard));
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
    telegram_contact: currentUser ? formatTelegramContact(currentUser) : formData.get("telegram_contact")?.trim(),
  };

  setStatus("Отправляем заявку...");
  orderForm.querySelector(".order-form__submit").disabled = true;

  try {
    const response = await fetch(apiUrl, {
      method: "POST",
      credentials: "include",
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

applyProfileLinks();
loadCurrentUser();
loadCatalog();
