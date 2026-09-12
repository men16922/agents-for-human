"""Bounded public catalog/order observations, excluding external IDs and raw content."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from rehearsal.world.storage import ContractError, Json, integer

if TYPE_CHECKING:
    from .gateway import Binding, StoreAPI

FIELDS = (
    "id,variants.id,variants.manage_inventory,variants.allow_backorder,"
    "variants.inventory_quantity,variants.calculated_price"
)


def number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("INVALID_CATALOG_AMOUNT")
    if not 0 <= value <= 2**53 - 1 or int(value) != value:
        raise ContractError("INVALID_CATALOG_AMOUNT")
    return int(value)


def catalog(binding: Binding, store: StoreAPI) -> Json:
    wanted = [
        (supplier, item, vid)
        for supplier, data in binding.suppliers.items()
        for item, vid in data["variants"].items()
        if item in binding.goal["items"]
    ]
    if not 1 <= len(wanted) <= 100 or len({v for _, _, v in wanted}) != len(wanted):
        raise ContractError("INVALID_CATALOG_SCOPE")
    params = [("variants[id][]", vid) for _, _, vid in wanted]
    params += [("region_id", binding.region_id), ("fields", FIELDS), ("limit", "100")]
    result = store.call("GET", "/store/products?" + urlencode(params))
    variants: dict[str, Json] = {}
    for product in result["products"]:
        for variant in product["variants"]:
            if variant["id"] in variants:
                raise ContractError("DUPLICATE_CATALOG_VARIANT")
            variants[variant["id"]] = variant
    offers = []
    for supplier, item, vid in wanted:
        offer: Json = {
            "supplier": supplier,
            "item": item,
            "status": "UNAVAILABLE",
            "stock": None,
            "unit_price": None,
            "currency": None,
            "inventory_managed": None,
            "backorder": None,
        }
        variant = variants.get(vid)
        if variant is not None:
            try:
                managed, backorder = variant["manage_inventory"], variant["allow_backorder"]
                if type(managed) is not bool or type(backorder) is not bool:
                    raise ValueError("Invalid flags")
                stock = number(variant["inventory_quantity"]) if managed else None
                price = variant.get("calculated_price")
                amount = None
                if price is not None:
                    if price["currency_code"] != "usd":
                        raise ValueError("Unsupported currency")
                    amount = number(price["calculated_amount"])
                offer.update(
                    status="OBSERVED",
                    stock=stock,
                    unit_price=amount,
                    currency="usd" if amount is not None else None,
                    inventory_managed=managed,
                    backorder=backorder,
                )
            except (KeyError, TypeError, ValueError):
                pass
        offers.append(offer)
    return {
        "status": "OBSERVED" if all(o["status"] == "OBSERVED" for o in offers) else "PARTIAL",
        "source": "medusa-store-sales-channel",
        "offers": offers,
    }


def public_details(value: Json, snapshot: Json) -> Json:
    """Whitelist and validate before durable publication; do not forward raw JSON."""
    try:
        cat, orders = value["catalog"], value["orders"]
        if value["receipt_status"] not in {"OBSERVED", "UNAVAILABLE"}:
            raise ValueError()
        if cat["status"] not in {"OBSERVED", "PARTIAL", "UNAVAILABLE"}:
            raise ValueError()
        if cat["source"] != "medusa-store-sales-channel" or len(cat["offers"]) > 100:
            raise ValueError()
        offers, seen = [], set()
        for offer in cat["offers"]:
            key = (offer["supplier"], offer["item"])
            if (
                key in seen
                or key[0] not in snapshot["suppliers"]
                or key[1] not in snapshot["goal"]["items"]
            ):
                raise ValueError()
            seen.add(key)
            if offer["status"] not in {"OBSERVED", "UNAVAILABLE"}:
                raise ValueError()
            for field in ("stock", "unit_price"):
                if offer[field] is not None:
                    number(offer[field])
            for field in ("inventory_managed", "backorder"):
                if offer[field] is not None and type(offer[field]) is not bool:
                    raise ValueError()
            if offer["currency"] not in {"usd", None}:
                raise ValueError()
            offers.append(
                {
                    k: offer[k]
                    for k in (
                        "supplier",
                        "item",
                        "status",
                        "stock",
                        "unit_price",
                        "currency",
                        "inventory_managed",
                        "backorder",
                    )
                }
            )
        if orders["status"] not in {"OBSERVED", "PARTIAL"} or len(orders["items"]) > 50:
            raise ValueError()
        total = integer(orders["total"])
        if total < len(orders["items"]) or orders["truncated"] is not (
            total > len(orders["items"])
        ):
            raise ValueError()
        items, ids = [], set()
        for order in orders["items"]:
            if (
                order["run_id"] != snapshot["run_id"]
                or order["supplier"] not in snapshot["suppliers"]
            ):
                raise ValueError()
            if (
                not isinstance(order["id"], str)
                or not 1 <= len(order["id"]) <= 128
                or order["id"] in ids
            ):
                raise ValueError()
            ids.add(order["id"])
            if order["status"] not in {"ACCEPTED", "PAID", "FULFILLING", "DELIVERED", "UNKNOWN"}:
                raise ValueError()
            if order["payment_status"] not in {"NOT_STARTED", "RESERVED", "SETTLED", "UNKNOWN"}:
                raise ValueError()
            for key, quantity in order["items"].items():
                if key not in snapshot["goal"]["items"]:
                    raise ValueError()
                integer(quantity, 1)
            number(order["amount"])
            integer(order["created_tick"])
            items.append(
                {
                    k: order[k]
                    for k in (
                        "id",
                        "run_id",
                        "supplier",
                        "items",
                        "amount",
                        "status",
                        "payment_status",
                        "created_tick",
                    )
                }
            )
        return {
            "receipt_status": value["receipt_status"],
            "catalog": {"status": cat["status"], "source": cat["source"], "offers": offers},
            "orders": {
                "status": orders["status"],
                "total": total,
                "truncated": orders["truncated"],
                "items": items,
            },
        }
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ContractError("INVALID_COMMERCE_OBSERVATION") from exc
