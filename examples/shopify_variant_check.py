#!/usr/bin/env python3
"""Check a Shopify product variant using the public product JSON endpoint.

This is intentionally stdlib-only so agents can copy it into constrained
execution environments.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class VariantNotFoundError(Exception):
    """Raised when a requested variant title is not present."""


class RateLimitedError(Exception):
    """Raised when the endpoint keeps returning a rate-limit status."""


# Shopify returns 430 (and sometimes 429/503) when it rate-limits storefront
# bot traffic. As of 2026 this is the common failure mode for automated reads.
RETRY_STATUSES = frozenset({429, 430, 503})

# Never sleep longer than this on a Retry-After header; a hostile or buggy
# server could otherwise stall the caller indefinitely.
MAX_RETRY_AFTER = 60.0


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


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    """Parse a Retry-After header (delta-seconds form), bounded and validated.

    Returns None for missing/invalid/negative/non-finite values so the caller
    falls back to exponential backoff. Caps the delay at ``MAX_RETRY_AFTER`` so a
    hostile or buggy header can't stall the caller.
    """
    value = exc.headers.get("Retry-After") if exc.headers else None
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, MAX_RETRY_AFTER)


def fetch_json(
    url: str,
    timeout: int = 15,
    retries: int = 3,
    backoff: float = 1.0,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "agent-fast-paths/1.0 (+https://github.com/jeffgreendesign/agent-fast-paths)",
            "Accept": "application/json,text/javascript,*/*;q=0.8",
            # Ask for uncompressed bytes; urllib does not transparently decode
            # gzip/br, so a compressing CDN would otherwise break json.loads.
            "Accept-Encoding": "identity",
        },
    )
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"expected a JSON object, got {type(data).__name__}")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_STATUSES and attempt < retries:
                delay = _retry_after_seconds(exc)
                if delay is None:
                    delay = backoff * (2**attempt)
                time.sleep(delay)
                attempt += 1
                continue
            if exc.code in RETRY_STATUSES:
                raise RateLimitedError(
                    f"rate_limited: HTTP {exc.code} after {retries} retries"
                ) from exc
            raise


def fetch_product(js_url: str, timeout: int = 15) -> tuple[dict[str, Any], str]:
    """Fetch a Shopify product, falling back from `.js` to `.json` if disabled.

    Some stores turn off the `.js` view but leave `/products/<handle>.json`
    reachable. The `.json` view wraps the product under a top-level `product`
    key, so unwrap it to return the same shape either way. Returns the product
    together with the URL that actually served it, so callers can report the
    live endpoint rather than the (possibly dead) `.js` URL.
    """
    try:
        return fetch_json(js_url, timeout=timeout), js_url
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 410):
            raise

    json_url = js_url[:-3] + ".json" if js_url.endswith(".js") else js_url
    data = fetch_json(json_url, timeout=timeout)
    if "variants" not in data and isinstance(data.get("product"), dict):
        return data["product"], json_url
    return data, json_url


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


def find_variant_by_options(product: dict[str, Any], option_values: list[str]) -> dict[str, Any]:
    """Find a variant by exact option values, e.g. Bright White + XL.

    Exact option equality avoids false matches like XL inside 2XL, 3XL, or XLT.
    Option order is ignored because Shopify stores vary by color/size ordering.
    """
    wanted = {value.strip() for value in option_values if value and value.strip()}
    if not wanted:
        raise VariantNotFoundError("empty option selection")

    matches: list[dict[str, Any]] = []
    for variant in product.get("variants", []):
        options = {
            str(value).strip()
            for value in (variant.get("option1"), variant.get("option2"), variant.get("option3"))
            if value is not None and str(value).strip()
        }
        title_parts = {
            part.strip() for part in str(variant.get("title", "")).split("/") if part.strip()
        }
        if wanted.issubset(options or title_parts):
            matches.append(variant)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise VariantNotFoundError(
            f"ambiguous option match ({len(matches)} variants); provide more --option values"
        )
    raise VariantNotFoundError(" + ".join(option_values))


def summarize_variant(
    product: dict[str, Any], variant: dict[str, Any], source_url: str
) -> dict[str, Any]:
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
    parser.add_argument("--variant", help="Exact variant title, e.g. 'Bright White / XL'")
    parser.add_argument(
        "--option",
        action="append",
        default=[],
        help="Exact option value to match, repeatable, e.g. --option 'Bright White' --option XL",
    )
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args(argv)

    if bool(args.variant) == bool(args.option):
        parser.error("provide exactly one of --variant or repeatable --option")

    try:
        json_url = product_json_url(args.url)
        product, source_url = fetch_product(json_url, timeout=args.timeout)
        variant = (
            find_variant(product, args.variant)
            if args.variant
            else find_variant_by_options(product, args.option)
        )
        result = summarize_variant(product, variant, source_url)
    except (
        ValueError,
        VariantNotFoundError,
        RateLimitedError,
        urllib.error.URLError,
        json.JSONDecodeError,
        TypeError,
    ) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
