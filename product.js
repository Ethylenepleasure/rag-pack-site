const detailRoot = document.querySelector("#product-detail");
const orderController = RagpackShop.initOrderForm();

const renderState = (title, message = "") => {
  detailRoot.innerHTML = `
    <section class="product-detail__state">
      <p class="section-label">object card</p>
      <h1>${RagpackShop.escapeHtml(title)}</h1>
      ${message ? `<p>${RagpackShop.escapeHtml(message)}</p>` : ""}
      <a class="hero__button" href="/#catalog">Вернуться в каталог</a>
    </section>
  `;
};

const createGallery = (product) => {
  const gallery = [{ image: product.image, alt: product.alt || product.name }, ...product.gallery]
    .filter((item, index, items) => item?.image && items.findIndex((candidate) => candidate.image === item.image) === index)
    .slice(0, 5);

  return gallery
    .map(
      (item, index) => `
        <figure class="product-detail__image ${index === 0 ? "product-detail__image--primary" : ""} ${
        index === 0 && product.image_fit === "contain" ? "product-detail__image--fit-contain" : ""
      }">
          <img src="${RagpackShop.escapeHtml(RagpackShop.getAssetUrl(item.image))}" alt="${RagpackShop.escapeHtml(item.alt || product.name)}" />
        </figure>
      `,
    )
    .join("");
};

const createSpecs = (product) => {
  const entries = Object.entries(product.specs);

  if (!entries.length) {
    return "";
  }

  return `
    <dl class="product-detail__specs">
      ${entries
        .map(
          ([label, value]) => `
            <div>
              <dt>${RagpackShop.escapeHtml(label)}</dt>
              <dd>${RagpackShop.escapeHtml(value)}</dd>
            </div>
          `,
        )
        .join("")}
    </dl>
  `;
};

const createFeatures = (product) => {
  if (!product.features.length) {
    return "";
  }

  return `
    <ul class="product-detail__features">
      ${product.features.map((feature) => `<li>${RagpackShop.escapeHtml(feature)}</li>`).join("")}
    </ul>
  `;
};

const createTitleMark = (product) =>
  product.title_mark === "blot"
    ? '<span class="product-detail__title-mark product-detail__title-mark--blot" aria-hidden="true"></span>'
    : "";

const createDisplayTitle = (product) => `
  <span class="product-detail__title-text">
    ${(product.display_name || product.name)
    .split("\n")
    .map((line) => `<span class="product-detail__title-line">${RagpackShop.escapeHtml(line)}</span>`)
    .join("")}
  </span>
  ${createTitleMark(product)}
`;

const renderProduct = (product) => {
  RagpackShop.updateProductSeo(product);

  detailRoot.innerHTML = `
    <section class="product-detail__layout" aria-labelledby="product-title">
      <div class="product-detail__gallery" aria-label="Изображения товара">
        ${createGallery(product)}
      </div>
      <article class="product-detail__content">
        <a class="product-detail__back" href="/#catalog">Назад в каталог</a>
        <p class="section-label">${RagpackShop.escapeHtml(product.tag || product.category)}</p>
        <h1 id="product-title" class="${product.title_size === "compact" ? "product-detail__title--compact" : ""}">${createDisplayTitle(product)}</h1>
        <strong class="product-detail__price">${RagpackShop.escapeHtml(product.price)}</strong>
        <p class="product-detail__description">${RagpackShop.escapeHtml(product.detail_description)}</p>
        ${createSpecs(product)}
        ${createFeatures(product)}
        ${product.notes ? `<p class="product-detail__notes">${RagpackShop.escapeHtml(product.notes)}</p>` : ""}
        <button class="order-form__submit product-detail__order" type="button">
          Заказать
        </button>
      </article>
    </section>
  `;

  detailRoot.querySelector(".product-detail__order").addEventListener("click", () => orderController.openOrderDialog(product));
};

const loadProduct = async () => {
  const slug = RagpackShop.getProductSlugFromLocation();

  if (!slug) {
    renderState("not found", "Не удалось определить товар.");
    return;
  }

  try {
    const products = await RagpackShop.fetchCatalog();
    const product = products.find((item) => item.slug === slug);

    if (!product) {
      renderState("not found", "Такого товара нет в каталоге.");
      return;
    }

    renderProduct(product);
  } catch (error) {
    console.warn("Product unavailable.", error);
    renderState("error", "Карточка товара временно не загрузилась.");
  }
};

loadProduct();
