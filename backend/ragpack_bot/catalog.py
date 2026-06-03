from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


REQUIRED_PRODUCT_FIELDS = ("slug", "name", "price", "image", "description")


@dataclass(frozen=True)
class Product:
    slug: str
    category: str
    tag: str
    name: str
    description: str
    price: str
    image: str
    alt: str
    display_name: str = ""
    title_mark: str = ""
    title_size: str = ""
    image_fit: str = "cover"
    detail_description: str = ""
    gallery: list[dict[str, str]] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    specs: dict[str, str] = field(default_factory=dict)
    notes: str = ""


class Catalog:
    def __init__(self, products: list[Product]) -> None:
        self.products = products
        self._by_slug = {product.slug: product for product in products}

    @classmethod
    def from_file(cls, path: Path) -> "Catalog":
        with path.open(encoding="utf-8") as file:
            rows = json.load(file)

        if not isinstance(rows, list):
            raise ValueError("Catalog must be a list")

        products: list[Product] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"Catalog row {index} must be an object")

            missing_fields = [
                field_name
                for field_name in REQUIRED_PRODUCT_FIELDS
                if not isinstance(row.get(field_name), str) or not row[field_name].strip()
            ]
            if missing_fields:
                raise ValueError(f"Catalog row {index} is missing required fields: {', '.join(missing_fields)}")

            products.append(Product(**row))

        return cls(products)

    def get(self, slug: str) -> Product | None:
        return self._by_slug.get(slug)

    def by_category(self, category: str) -> list[Product]:
        return [product for product in self.products if product.category == category]
