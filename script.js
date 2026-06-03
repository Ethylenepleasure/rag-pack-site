const productGrid = document.querySelector("#product-grid");
const orderController = RagpackShop.initOrderForm();

const renderCatalogState = (message, type = "") => {
  productGrid.innerHTML = `
    <p class="catalog__fallback" data-type="${RagpackShop.escapeHtml(type)}">
      ${RagpackShop.escapeHtml(message)}
    </p>
  `;
};

const createProductCard = (product) => {
  const card = document.createElement("article");
  card.className = "product-card";
  const productUrl = RagpackShop.getProductUrl(product);
  card.innerHTML = `
    <a class="product-card__link" href="${RagpackShop.escapeHtml(productUrl)}" aria-label="Подробнее о ${RagpackShop.escapeHtml(product.name)}">
      <span class="product-card__image">
        <img src="${RagpackShop.escapeHtml(RagpackShop.getAssetUrl(product.image))}" alt="${RagpackShop.escapeHtml(product.alt || product.name)}" />
      </span>
      <span class="product-card__body">
        <span class="product-card__tag">${RagpackShop.escapeHtml(product.tag || product.category)}</span>
        <h3>${RagpackShop.escapeHtml(product.name)}</h3>
        <p>${RagpackShop.escapeHtml(product.description)}</p>
      </span>
    </a>
    <div class="product-card__bottom">
      <strong>${RagpackShop.escapeHtml(product.price)}</strong>
      <div class="product-card__actions">
        <a class="product-card__details" href="${RagpackShop.escapeHtml(productUrl)}">Подробнее</a>
        <button type="button" aria-label="Заказать ${RagpackShop.escapeHtml(product.name)}">Заказать</button>
      </div>
    </div>
  `;

  card.querySelector("button").addEventListener("click", () => orderController.openOrderDialog(product));
  return card;
};

const loadCatalog = async () => {
  renderCatalogState("Загружаем каталог...");

  try {
    const products = await RagpackShop.fetchCatalog();
    productGrid.replaceChildren(...products.map(createProductCard));
  } catch (error) {
    console.warn("Catalog unavailable.", error);
    renderCatalogState("Каталог временно не загрузился. Для заказа напишите креэйтору в Telegram.", "error");
  }
};

loadCatalog();
