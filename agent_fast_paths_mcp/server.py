"""MCP server exposing the web-platform fast paths as agent tools.

Wraps the stdlib-only example modules (loaded via ``_load``) so any
MCP-compatible agent can call them directly instead of copy-pasting scripts.
Every tool is strictly read-only: it never touches carts, checkout, auth, or
any state-changing endpoint, and it returns structured ``{"ok": false, ...}``
errors instead of raising, matching the example CLIs.
"""

from __future__ import annotations

import dataclasses
import html
import re
import urllib.error
import urllib.parse
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._load import probe as _probe
from ._load import shopify as _shopify

mcp = FastMCP("agent-fast-paths")


def _error(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": message, **extra}


def _site_root(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Expected an absolute URL, e.g. https://store.example.com")
    return f"{parsed.scheme}://{parsed.netloc}"


@mcp.tool()
def probe_platform(url: str, timeout: int = 15) -> dict[str, Any]:
    """Cheaply guess a page's platform and suggest structured-data endpoints.

    Fetches the page (read-only), inspects URL shape, HTML markers, and JSON-LD,
    and returns likely platforms plus fast-path endpoints worth trying next.
    """
    try:
        text = _probe.fetch_text(url, timeout=timeout)
        result = _probe.probe(url, text)
    except Exception as exc:  # mirror the probe CLI: never crash the agent
        return _error(str(exc))
    return {"ok": True, **dataclasses.asdict(result)}


@mcp.tool()
def shopify_check_variant(
    url: str,
    variant: str | None = None,
    options: list[str] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    """Verify one Shopify product variant via the public product JSON.

    Provide exactly one of ``variant`` (exact title, e.g. "Bright White / XL")
    or ``options`` (exact option values, e.g. ["Bright White", "XL"]). Exact
    option equality avoids false matches like XL inside 2XL/3XL/XLT. Returns the
    verified variant with availability and price (dollars and cents).
    """
    if bool(variant) == bool(options):
        return _error("provide exactly one of 'variant' or 'options'")
    try:
        json_url = _shopify.product_json_url(url)
        product = _shopify.fetch_product(json_url, timeout=timeout)
        matched = (
            _shopify.find_variant(product, variant)
            if variant
            else _shopify.find_variant_by_options(product, options or [])
        )
        summary = _shopify.summarize_variant(product, matched, json_url)
    except (
        ValueError,
        _shopify.VariantNotFoundError,
        _shopify.RateLimitedError,
        urllib.error.URLError,
        TypeError,
    ) as exc:
        return _error(str(exc))
    return {"ok": True, **summary}


def _has_available_variant(product: dict[str, Any], options: list[str]) -> dict[str, Any] | None:
    """Return the matching available variant for these exact options, else None."""
    try:
        variant = _shopify.find_variant_by_options(product, options)
    except _shopify.VariantNotFoundError:
        return None
    return variant if variant.get("available") is True else None


@mcp.tool()
def shopify_find_available(
    base_url: str,
    color: str,
    size: str,
    need: int = 3,
    collections: list[str] | None = None,
    max_handles: int = 60,
    timeout: int = 15,
) -> dict[str, Any]:
    """Find N Shopify products available in an exact color + size.

    Codifies the fast-path hunt: try any provided collection JSON first, then
    discover product handles from the sitemap, then verify each candidate via
    ``/products/<handle>.js``. Read-only; stops as soon as ``need`` exact,
    available matches are found. Returns matches plus notes on what was tried.
    """
    options = [color, size]
    notes: list[str] = []
    try:
        root = _site_root(base_url)
    except ValueError as exc:
        return _error(str(exc))

    matches: list[dict[str, Any]] = []
    seen_handles: set[str] = set()

    def consider(product: dict[str, Any], handle: str) -> None:
        variant = _has_available_variant(product, options)
        if variant is None:
            return
        matches.append(
            {
                "product": product.get("title"),
                "handle": product.get("handle") or handle,
                "url": f"{root}/products/{product.get('handle') or handle}",
                "variant": variant.get("title"),
                "available": variant.get("available"),
                "price": _shopify.normalize_price(variant.get("price"))[1],
                "variant_id": variant.get("id"),
            }
        )

    # 1) Provided collections: their JSON already includes full variant data.
    for coll in collections or []:
        if len(matches) >= need:
            break
        coll_url = f"{root}/collections/{coll}/products.json?limit=250"
        try:
            data = _shopify.fetch_json(coll_url, timeout=timeout)
        except (urllib.error.URLError, _shopify.RateLimitedError, ValueError) as exc:
            notes.append(f"collection '{coll}' failed: {exc}")
            continue
        for product in data.get("products", []):
            handle = product.get("handle", "")
            if handle in seen_handles:
                continue
            seen_handles.add(handle)
            consider(product, handle)
            if len(matches) >= need:
                break

    # 2) Sitemap discovery -> per-handle .js verification.
    if len(matches) < need:
        handles = _discover_handles_from_sitemap(root, timeout, notes)
        for handle in handles:
            if len(matches) >= need or len(seen_handles) >= max_handles:
                break
            if handle in seen_handles:
                continue
            seen_handles.add(handle)
            try:
                product = _shopify.fetch_product(f"{root}/products/{handle}.js", timeout=timeout)
            except (urllib.error.URLError, _shopify.RateLimitedError, ValueError):
                continue
            consider(product, handle)

    return {
        "ok": True,
        "requested": {"color": color, "size": size, "need": need},
        "found": len(matches),
        "matches": matches[:need],
        "notes": notes,
    }


_LOC_RE = re.compile(r"<loc>([^<]+)</loc>", re.IGNORECASE)


def _discover_handles_from_sitemap(root: str, timeout: int, notes: list[str]) -> list[str]:
    try:
        index = _probe.fetch_text(f"{root}/sitemap.xml", timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - discovery is best-effort
        notes.append(f"sitemap.xml unavailable: {exc}")
        return []

    product_sitemaps = [
        html.unescape(loc) for loc in _LOC_RE.findall(index) if "sitemap_products_" in loc
    ]
    handles: list[str] = []
    seen: set[str] = set()
    for sm_url in product_sitemaps:
        try:
            text = _probe.fetch_text(sm_url, timeout=timeout)
        except Exception:  # noqa: BLE001
            continue
        for loc in _LOC_RE.findall(text):
            path = urllib.parse.urlparse(html.unescape(loc)).path
            if "/products/" not in path:
                continue
            handle = path.rsplit("/products/", 1)[-1].strip("/")
            if handle and handle not in seen:
                seen.add(handle)
                handles.append(handle)
    if not handles:
        notes.append("no product handles discovered from sitemap")
    return handles


def main() -> None:
    """Console entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
