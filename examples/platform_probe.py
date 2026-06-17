#!/usr/bin/env python3
"""Lightweight platform probe for public web fast paths.

This script does not prove a site is on a platform. It gives an agent a cheap
first pass: URL shape, obvious HTML markers, JSON-LD types, and likely next
endpoints to try.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class ProbeResult:
    url: str
    likely_platforms: list[str]
    json_ld_types: list[str]
    suggested_fast_paths: list[str]
    notes: list[str]


def fetch_text(url: str, timeout: int = 15) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "agent-fast-paths/1.0 (+https://github.com/jeffgreendesign/agent-fast-paths)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(1_000_000)
    return raw.decode("utf-8", errors="replace")


def extract_json_ld_types(text: str) -> list[str]:
    types: set[str] = set()
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        body = html.unescape(match.group(1)).strip()
        if not body:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        collect_types(data, types)
    return sorted(types)


def collect_types(value: Any, types: set[str]) -> None:
    if isinstance(value, dict):
        kind = value.get("@type")
        if isinstance(kind, str):
            types.add(kind)
        elif isinstance(kind, list):
            types.update(str(item) for item in kind)
        for child in value.values():
            collect_types(child, types)
    elif isinstance(value, list):
        for item in value:
            collect_types(item, types)


def product_handle_from_url(url: str) -> str | None:
    parts = [part for part in urllib.parse.urlparse(url).path.split("/") if part]
    try:
        idx = parts.index("products")
        handle = parts[idx + 1]
    except (ValueError, IndexError):
        return None
    return handle.removesuffix(".js")


def probe(url: str, text: str) -> ProbeResult:
    lower = text.lower()
    parsed = urllib.parse.urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    platforms: list[str] = []
    paths: list[str] = []
    notes: list[str] = []

    handle = product_handle_from_url(url)
    if handle:
        platforms.append("shopify-or-shopify-like")
        paths.append(f"{root}/products/{handle}.js")
        notes.append("URL contains /products/<handle>; try Shopify product JSON first.")

    if "cdn.shopify.com" in lower or "shopify-section" in lower or "shopify-features" in lower:
        platforms.append("shopify")
        paths.extend([f"{root}/products.json?limit=250", f"{root}/sitemap_products_1.xml"])

    if "wp-content" in lower or "wp-json" in lower or "woocommerce" in lower:
        platforms.append("wordpress-or-woocommerce")
        paths.extend([f"{root}/wp-json/wp/v2/search?search=QUERY", f"{root}/wp-json/wc/store/v1/products?search=QUERY"])

    if "__next_data__" in lower or 'id="__next_data__"' in lower:
        platforms.append("nextjs")
        notes.append("Extract the __NEXT_DATA__ script JSON before browser automation.")

    if "window.__nuxt__" in lower or "/_nuxt/" in lower or "_payload.json" in lower:
        platforms.append("nuxt")
        notes.append("Look for Nuxt payload files or window.__NUXT__ state.")

    json_ld_types = extract_json_ld_types(text)
    if json_ld_types:
        notes.append("JSON-LD found; inspect relevant schema objects before generic extraction.")
    if any(kind in json_ld_types for kind in ["Product", "Offer", "AggregateOffer"]):
        platforms.append("json-ld-product")
    if "JobPosting" in json_ld_types:
        platforms.append("json-ld-job-posting")

    return ProbeResult(
        url=url,
        likely_platforms=sorted(set(platforms)),
        json_ld_types=json_ld_types,
        suggested_fast_paths=dedupe(paths),
        notes=dedupe(notes),
    )


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args(argv)

    try:
        text = fetch_text(args.url, timeout=args.timeout)
        result = probe(args.url, text)
    except Exception as exc:  # probe helper; return structured error for agents
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
