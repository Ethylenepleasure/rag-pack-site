from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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


class Catalog:
    def __init__(self, products: list[Product]) -> None:
        self.products = products
        self._by_slug = {product.slug: product for product in products}

    @classmethod
    def from_file(cls, path: Path) -> "Catalog":
        with path.open(encoding="utf-8") as file:
            rows = json.load(file)

        return cls([Product(**row) for row in rows])

    def get(self, slug: str) -> Product | None:
        return self._by_slug.get(slug)

    def by_category(self, category: str) -> list[Product]:
        return [product for product in self.products if product.category == category]
