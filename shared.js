const RagpackShop = (() => {
  const requiredProductFields = ["slug", "name", "price", "image", "description"];

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

  const apiUrl = document.querySelector('meta[name="ragpack-api-url"]')?.content || "/api/orders";
  const apiBaseUrl = new URL(apiUrl, window.location.href);
  const profileUrl = new URL("/profile", apiBaseUrl);
  const profileApiUrl = new URL("/api/profile", apiBaseUrl).toString();

  const isValidProduct = (product) =>
    product &&
    typeof product === "object" &&
    requiredProductFields.every((field) => typeof product[field] === "string" && product[field].trim());

  const normalizeProduct = (product) => ({
    ...product,
    gallery: Array.isArray(product.gallery) ? product.gallery.filter((item) => item?.image) : [],
    features: Array.isArray(product.features) ? product.features.filter(Boolean) : [],
    specs: product.specs && typeof product.specs === "object" ? product.specs : {},
    detail_description: product.detail_description || product.description,
    notes: product.notes || "",
  });

  const fetchCatalog = async () => {
    const response = await fetch(new URL("/catalog.json?v=product-pages-6", window.location.origin), { cache: "no-store" });

    if (!response.ok) {
      throw new Error("catalog request failed");
    }

    const products = await response.json();

    if (!Array.isArray(products)) {
      throw new Error("catalog must be an array");
    }

    const normalizedProducts = products.filter(isValidProduct).map(normalizeProduct);

    if (!normalizedProducts.length) {
      throw new Error("catalog is empty or invalid");
    }

    return normalizedProducts;
  };

  const getProductUrl = (product) => {
    if (apiBaseUrl.origin === window.location.origin) {
      return `/product/${encodeURIComponent(product.slug)}`;
    }

    return `/product.html?slug=${encodeURIComponent(product.slug)}`;
  };

  const getAssetUrl = (path) => {
    if (!path || /^https?:\/\//i.test(path) || path.startsWith("/")) {
      return path || "";
    }

    return `/${path}`;
  };

  const getProductSlugFromLocation = () => {
    const pathMatch = window.location.pathname.match(/\/product\/([^/]+)\/?$/);

    if (pathMatch) {
      return decodeURIComponent(pathMatch[1]);
    }

    return new URLSearchParams(window.location.search).get("slug") || "";
  };

  const setMeta = (selector, attribute, value) => {
    let element = document.querySelector(selector);

    if (!element && selector.startsWith('meta[')) {
      element = document.createElement("meta");
      const nameMatch = selector.match(/name="([^"]+)"/);
      const propertyMatch = selector.match(/property="([^"]+)"/);

      if (nameMatch) {
        element.setAttribute("name", nameMatch[1]);
      }

      if (propertyMatch) {
        element.setAttribute("property", propertyMatch[1]);
      }

      document.head.append(element);
    }

    if (element) {
      element.setAttribute(attribute, value);
    }
  };

  const updateProductSeo = (product) => {
    const title = `${product.name} / RĄG PACK//`;
    const description = product.detail_description || product.description;
    const canonicalUrl = new URL(getProductUrl(product), window.location.origin).toString();
    const imageUrl = new URL(getAssetUrl(product.image), window.location.origin).toString();

    document.title = title;
    setMeta('meta[name="description"]', "content", description);
    setMeta('meta[property="og:title"]', "content", title);
    setMeta('meta[property="og:description"]', "content", description);
    setMeta('meta[property="og:image"]', "content", imageUrl);
    setMeta('meta[property="og:url"]', "content", canonicalUrl);

    let canonical = document.querySelector('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement("link");
      canonical.rel = "canonical";
      document.head.append(canonical);
    }
    canonical.href = canonicalUrl;
  };

  const formatTelegramContact = (user) => {
    if (!user) {
      return "";
    }

    return user.telegram_username ? `@${user.telegram_username}` : String(user.telegram_user_id || "");
  };

  const initOrderForm = () => {
    const dialog = document.querySelector("#order");
    const orderForm = document.querySelector("#order-form");
    const selectedProduct = document.querySelector("#selected-product");
    const orderStatus = document.querySelector("#order-status");
    const closeButton = document.querySelector(".order-form__close");
    const telegramContactField = document.querySelector("#telegram-contact-field");
    const telegramContactInput = orderForm?.querySelector('[name="telegram_contact"]');
    const profileTelegramContact = document.querySelector("#profile-telegram-contact");
    const profileLink = document.querySelector("#profile-link");
    const ordersLink = document.querySelector("#orders-link");

    let selectedProductData = null;
    let currentUser = null;

    const setStatus = (message, type = "") => {
      if (!orderStatus) {
        return;
      }

      orderStatus.textContent = message;
      orderStatus.dataset.type = type;
    };

    const applyProfileToOrderForm = () => {
      const telegramContact = formatTelegramContact(currentUser);

      if (telegramContactField && telegramContactInput && profileTelegramContact) {
        telegramContactField.hidden = Boolean(telegramContact);
        telegramContactInput.required = !telegramContact;
        telegramContactInput.value = telegramContact;
        profileTelegramContact.hidden = !telegramContact;
        profileTelegramContact.textContent = telegramContact ? `Telegram: ${telegramContact}` : "";
      }
    };

    const applyProfileLinks = () => {
      const profileHref = profileUrl.toString();
      const ordersHref = new URL(profileUrl);
      ordersHref.hash = currentUser ? "profile-orders" : "auth-panel";

      if (profileLink) {
        profileLink.href = profileHref;
      }

      if (ordersLink) {
        ordersLink.href = ordersHref.toString();
      }
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
      if (!dialog || !orderForm || !selectedProduct) {
        return;
      }

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

    closeButton?.addEventListener("click", () => {
      if (typeof dialog?.close === "function") {
        dialog.close();
      }
    });

    orderForm?.addEventListener("submit", async (event) => {
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

    return {
      openOrderDialog,
      loadCurrentUser,
    };
  };

  return {
    escapeHtml,
    fetchCatalog,
    getAssetUrl,
    getProductSlugFromLocation,
    getProductUrl,
    initOrderForm,
    updateProductSeo,
  };
})();
