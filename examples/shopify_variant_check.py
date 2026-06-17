#!/usr/bin/env python3
"""Check a Shopify product variant using the public product JSON endpoint.

This is intentionally stdlib-only so agents can copy it into constrained
execution environments.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class VariantNotFoundError(Exception):
    """Raised when a requested variant title is not present."""


def product_json_url(url: str) -> str:
    """Convert a Shopify product URL or product JSON URL to /products/<handle>.js."""
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Expected an absolute product URL, e.g. https://store.com/products/handle")

    path = parsed.path.rstrip("/")
    if path.endswith(".js") and "/products/" in path:
        normalized_path = path
    else:
        parts = [part for part in path.split("/") if part]
        try:
            product_index = parts.index("products")
            handle = parts[product_index + 1]
        except (ValueError, IndexError) as exc:
            raise ValueError("URL does not look like a Shopify product URL") from exc
        normalized_path = f"/products/{handle}.js"

    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, normalized_path, "", "", ""))


def fetch_json(url: str, timeout: int = 15) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "agent-fast-paths/1.0 (+https://github.com/jeffgreendesign/agent-fast-paths)",
            "Accept": "application/json,text/javascript,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_price(price: Any) -> tuple[int | None, float | None]:
    """Return (price_cents, price_dollars) for Shopify-ish price values."""
    if price is None:
        return None, None
    if isinstance(price, int):
        return price, price / 100
    if isinstance(price, float):
        # Some APIs expose decimal dollars; Shopify product .js normally does not.
        return int(round(price * 100)), price
    if isinstance(price, str):
        cleaned = price.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return None, None
        if "." in cleaned:
            dollars = float(cleaned)
            return int(round(dollars * 100)), dollars
        cents = int(cleaned)
        return cents, cents / 100
    raise TypeError(f"Unsupported price type: {type(price).__name__}")


def find_variant(product: dict[str, Any], variant_title: str) -> dict[str, Any]:
    for variant in product.get("variants", []):
        if variant.get("title") == variant_title:
            return variant
    raise VariantNotFoundError(variant_title)


def summarize_variant(product: dict[str, Any], variant: dict[str, Any], source_url: str) -> dict[str, Any]:
    price_cents, price = normalize_price(variant.get("price"))
    return {
        "product": product.get("title"),
        "handle": product.get("handle"),
        "source_url": source_url,
        "variant": variant.get("title"),
        "available": variant.get("available"),
        "price": price,
        "price_cents": price_cents,
        "variant_id": variant.get("id"),
        "sku": variant.get("sku") or None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Shopify product URL or /products/<handle>.js URL")
    parser.add_argument("--variant", required=True, help="Exact variant title, e.g. 'Bright White / XL'")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args(argv)

    try:
        json_url = product_json_url(args.url)
        product = fetch_json(json_url, timeout=args.timeout)
        variant = find_variant(product, args.variant)
        result = summarize_variant(product, variant, json_url)
    except (ValueError, VariantNotFoundError, urllib.error.URLError, json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
