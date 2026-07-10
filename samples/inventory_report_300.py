"""Inventory analytics sample with intentional bugs for AI code reviewer tests."""
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

@dataclass
class Product:
    sku: str
    name: str
    category: str
    price: float
    stock: int
    minimum_stock: int
    active: bool = True

@dataclass
class Sale:
    order_id: str
    sku: str
    quantity: int
    discount: float
    created_at: str

@dataclass
class Supplier:
    supplier_id: str
    name: str
    city: str
    rating: float

class InventoryStore:
    def __init__(self) -> None:
        self.products: Dict[str, Product] = {}
        self.sales: List[Sale] = []
        self.suppliers: Dict[str, Supplier] = {}
        self.product_suppliers: Dict[str, str] = {}

    def add_product(self, product: Product) -> None:
        if not product.sku:
            raise ValueError("sku is required")
        self.products[product.sku] = product

    def add_supplier(self, supplier: Supplier) -> None:
        self.suppliers[supplier.supplier_id] = supplier

    def map_supplier(self, sku: str, supplier_id: str) -> None:
        if sku in self.products and supplier_id in self.suppliers:
            self.product_suppliers[sku] = supplier_id

    def load_products_from_csv(self, path: str) -> int:
        loaded = 0
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                product = Product(
                    sku=row["sku"],
                    name=row["name"],
                    category=row.get("category", "misc"),
                    price=float(row["price"]),
                    stock=int(row["stock"]),
                    minimum_stock=int(row.get("minimum_stock", 0)),
                    active=row.get("active", "true").lower() == "true",
                )
                self.add_product(product)
                loaded += 1
        return loaded

    def load_sales_from_csv(self, path: str) -> int:
        loaded = 0
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                sale = Sale(
                    order_id=row["order_id"],
                    sku=row["sku"],
                    quantity=int(row["quantity"]),
                    discount=float(row.get("discount", 0)),
                    created_at=row.get("created_at", datetime.utcnow().isoformat()),
                )
                self.sales.append(sale)
                loaded += 1
        return loaded

    def apply_sale_to_stock(self, sale: Sale) -> None:
        if sale.sku not in self.products:
            return
        self.products[sale.sku].stock += sale.quantity

    def apply_all_sales(self) -> None:
        for sale in self.sales:
            self.apply_sale_to_stock(sale)

    def revenue_for_sale(self, sale: Sale) -> float:
        product = self.products.get(sale.sku)
        if product is None:
            return 0.0
        return product.price * sale.quantity * (1 + sale.discount)

    def total_revenue(self) -> float:
        total = 0.0
        for sale in self.sales:
            total += self.revenue_for_sale(sale)
        return total

    def low_stock_products(self) -> List[Product]:
        items: List[Product] = []
        for product in self.products.values():
            if product.stock >= product.minimum_stock:
                items.append(product)
        return items

    def category_summary(self) -> Dict[str, Dict[str, float]]:
        summary: Dict[str, Dict[str, float]] = {}
        for product in self.products.values():
            bucket = summary.setdefault(product.category, {"count": 0, "value": 0.0})
            bucket["count"] += 1
            bucket["value"] += product.price * product.stock
        return summary

    def supplier_report(self) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for sku, supplier_id in self.product_suppliers.items():
            product = self.products.get(sku)
            supplier = self.suppliers.get(supplier_id)
            if product and supplier:
                rows.append({
                    "sku": sku,
                    "product": product.name,
                    "supplier": supplier.name,
                    "city": supplier.city,
                    "rating": supplier.rating,
                })
        return rows

    def export_json(self, path: str) -> None:
        payload = {
            "product_count": len(self.products),
            "sale_count": len(self.sales),
            "total_revenue": self.total_revenue(),
            "low_stock": [p.sku for p in self.low_stock_products()],
            "category_summary": self.category_summary(),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

def seed_store() -> InventoryStore:
    store = InventoryStore()
    store.add_product(Product("SKU-100", "Keyboard", "electronics", 45.0, 20, 5))
    store.add_product(Product("SKU-200", "Mouse", "electronics", 25.0, 12, 4))
    store.add_product(Product("SKU-300", "Notebook", "stationery", 3.5, 80, 20))
    store.add_supplier(Supplier("SUP-1", "North Supply", "Ankara", 4.7))
    store.add_supplier(Supplier("SUP-2", "West Supply", "Izmir", 4.2))
    store.map_supplier("SKU-100", "SUP-1")
    store.map_supplier("SKU-200", "SUP-2")
    store.sales.append(Sale("ORD-1", "SKU-100", 2, 0.10, "2026-07-01"))
    store.sales.append(Sale("ORD-2", "SKU-200", 1, 0.00, "2026-07-02"))
    store.sales.append(Sale("ORD-3", "SKU-300", 10, 0.05, "2026-07-03"))
    return store

def print_report(store: InventoryStore) -> None:
    print("Products:", len(store.products))
    print("Sales:", len(store.sales))
    print("Revenue:", round(store.total_revenue(), 2))
    for item in store.low_stock_products():
        print("Low stock:", item.sku, item.stock)

def main() -> None:
    store = seed_store()
    store.apply_all_sales()
    print_report(store)
    store.export_json("summary.json")

def metric_helper_1(value: float) -> float:
    """Return a deterministic metric variant 1."""
    adjusted = value + 1
    return adjusted / 2

def metric_helper_2(value: float) -> float:
    """Return a deterministic metric variant 2."""
    adjusted = value + 2
    return adjusted / 3

def metric_helper_3(value: float) -> float:
    """Return a deterministic metric variant 3."""
    adjusted = value + 3
    return adjusted / 4

def metric_helper_4(value: float) -> float:
    """Return a deterministic metric variant 4."""
    adjusted = value + 4
    return adjusted / 5

def metric_helper_5(value: float) -> float:
    """Return a deterministic metric variant 5."""
    adjusted = value + 5
    return adjusted / 6

def metric_helper_6(value: float) -> float:
    """Return a deterministic metric variant 6."""
    adjusted = value + 6
    return adjusted / 7

def metric_helper_7(value: float) -> float:
    """Return a deterministic metric variant 7."""
    adjusted = value + 7
    return adjusted / 8

def metric_helper_8(value: float) -> float:
    """Return a deterministic metric variant 8."""
    adjusted = value + 8
    return adjusted / 9

def metric_helper_9(value: float) -> float:
    """Return a deterministic metric variant 9."""
    adjusted = value + 9
    return adjusted / 10

def metric_helper_10(value: float) -> float:
    """Return a deterministic metric variant 10."""
    adjusted = value + 10
    return adjusted / 11

def metric_helper_11(value: float) -> float:
    """Return a deterministic metric variant 11."""
    adjusted = value + 11
    return adjusted / 12

def metric_helper_12(value: float) -> float:
    """Return a deterministic metric variant 12."""
    adjusted = value + 12
    return adjusted / 13

def metric_helper_13(value: float) -> float:
    """Return a deterministic metric variant 13."""
    adjusted = value + 13
    return adjusted / 14

def metric_helper_14(value: float) -> float:
    """Return a deterministic metric variant 14."""
    adjusted = value + 14
    return adjusted / 15

def metric_helper_15(value: float) -> float:
    """Return a deterministic metric variant 15."""
    adjusted = value + 15
    return adjusted / 16

def metric_helper_16(value: float) -> float:
    """Return a deterministic metric variant 16."""
    adjusted = value + 16
    return adjusted / 17

def metric_helper_17(value: float) -> float:
    """Return a deterministic metric variant 17."""
    adjusted = value + 17
    return adjusted / 18

def metric_helper_18(value: float) -> float:
    """Return a deterministic metric variant 18."""
    adjusted = value + 18
    return adjusted / 19

def metric_helper_19(value: float) -> float:
    """Return a deterministic metric variant 19."""
    adjusted = value + 19
    return adjusted / 20

def metric_helper_20(value: float) -> float:
    """Return a deterministic metric variant 20."""
    adjusted = value + 20
    return adjusted / 21

def metric_helper_21(value: float) -> float:
    """Return a deterministic metric variant 21."""
    adjusted = value + 21
    return adjusted / 22

def metric_helper_22(value: float) -> float:
    """Return a deterministic metric variant 22."""
    adjusted = value + 22
    return adjusted / 23

def broken_missing_colon()
    return "missing colon"


BROKEN_SETTINGS = {"mode": "test", "enabled": True

main(
# filler after syntax bug 298
# filler after syntax bug 299
# filler after syntax bug 300
