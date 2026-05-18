const dialog = document.querySelector("#order");
const selectedProduct = document.querySelector("#selected-product");
const orderButtons = document.querySelectorAll("[data-product]");

orderButtons.forEach((button) => {
  button.addEventListener("click", () => {
    selectedProduct.textContent = button.dataset.product;

    if (typeof dialog.showModal === "function") {
      dialog.showModal();
      return;
    }

    window.location.hash = "order";
  });
});
