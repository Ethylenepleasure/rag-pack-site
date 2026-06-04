from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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
    is_published: bool = True
    is_archived: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


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

            products.append(Product(**_product_payload(row)))

        return cls(products)

    def get(self, slug: str) -> Product | None:
        return self._by_slug.get(slug)

    def by_category(self, category: str) -> list[Product]:
        return [product for product in self.products if product.category == category]


class RuntimeCatalog:
    def __init__(self, storage: object, *, public_only: bool = True) -> None:
        self.storage = storage
        self.public_only = public_only

    @property
    def products(self) -> list[Product]:
        return self.storage.list_products(public_only=self.public_only)

    def get(self, slug: str) -> Product | None:
        return self.storage.get_product(slug, public_only=self.public_only)

    def by_category(self, category: str) -> list[Product]:
        return self.storage.by_product_category(category, public_only=self.public_only)


def _string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _gallery(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    gallery: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        image = _string(item.get("image"))
        if not image:
            continue

        gallery.append({"image": image, "alt": _string(item.get("alt"))})

    return gallery


def _features(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _specs(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    return {
        str(key).strip(): str(item).strip()
        for key, item in value.items()
        if str(key).strip() and str(item).strip()
    }


def _product_payload(row: dict[str, object]) -> dict[str, object]:
    return {
        "slug": _string(row.get("slug")),
        "category": _string(row.get("category")),
        "tag": _string(row.get("tag")),
        "name": _string(row.get("name")),
        "description": _string(row.get("description")),
        "price": _string(row.get("price")),
        "image": _string(row.get("image")),
        "alt": _string(row.get("alt")),
        "display_name": _string(row.get("display_name")),
        "title_mark": _string(row.get("title_mark")),
        "title_size": _string(row.get("title_size")),
        "image_fit": _string(row.get("image_fit")) or "cover",
        "detail_description": _string(row.get("detail_description")),
        "gallery": _gallery(row.get("gallery")),
        "features": _features(row.get("features")),
        "specs": _specs(row.get("specs")),
        "notes": _string(row.get("notes")),
        "is_published": bool(row.get("is_published", True)),
        "is_archived": bool(row.get("is_archived", False)),
        "created_at": _string(row.get("created_at")),
        "updated_at": _string(row.get("updated_at")),
    }
