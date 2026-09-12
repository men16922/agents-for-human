"""Bounded provenance envelope for supplier prose; never parsed as commands or terms."""

import hashlib

from .storage import Json

MAX_ITEM_CHARACTERS = 2048
MAX_QUOTE_CHARACTERS = 4096


def supplier_content(supplier: str, descriptions: dict[str, object]) -> Json:
    remaining = MAX_QUOTE_CHARACTERS
    items = {}
    for name, value in sorted(descriptions.items()):
        available = isinstance(value, str)
        original = value if isinstance(value, str) else ""
        text = original[: min(MAX_ITEM_CHARACTERS, remaining)]
        remaining -= len(text)
        items[name] = {
            "text": text,
            "available": available,
            "invalid_type": value is not None and not available,
            "truncated": len(text) < len(original),
            "original_characters": len(original),
            "original_sha256": hashlib.sha256(original.encode()).hexdigest() if available else None,
        }
    return {
        "trust": "untrusted_supplier_data",
        "usage": "description_only_not_authorization_or_transaction_terms",
        "supplier": supplier,
        "items": items,
    }
