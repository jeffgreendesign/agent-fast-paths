from __future__ import annotations

import json
import pathlib

import pytest

pytest.importorskip("mcp", reason="MCP extra not installed")

from agent_fast_paths_mcp import server  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "shopify_product.json").read_text())


def test_tools_are_registered() -> None:
    # FastMCP exposes registered tools via its (async) list; assert on the
    # underlying manager so the test stays synchronous.
    names = set(server.mcp._tool_manager._tools)
    assert {"probe_platform", "shopify_check_variant", "shopify_find_available"} <= names


def test_shopify_check_variant_matches_xl_not_2xl(monkeypatch) -> None:
    monkeypatch.setattr(server._shopify, "fetch_product", lambda *a, **k: FIXTURE)
    result = server.shopify_check_variant(
        "https://example.com/products/classic-t-shirt",
        options=["Bright White", "XL"],
    )
    assert result["ok"] is True
    assert result["variant"] == "Bright White / XL"
    assert result["variant_id"] == 102
    assert result["available"] is True
    assert result["price"] == 15.0
    assert result["price_cents"] == 1500


def test_shopify_check_variant_requires_exactly_one_selector() -> None:
    both = server.shopify_check_variant(
        "https://example.com/products/x", variant="a", options=["b"]
    )
    assert both["ok"] is False
    neither = server.shopify_check_variant("https://example.com/products/x")
    assert neither["ok"] is False


def test_shopify_check_variant_reports_missing_variant(monkeypatch) -> None:
    monkeypatch.setattr(server._shopify, "fetch_product", lambda *a, **k: FIXTURE)
    result = server.shopify_check_variant(
        "https://example.com/products/classic-t-shirt",
        options=["Bright White", "3XL"],
    )
    assert result["ok"] is False


def test_probe_platform_wraps_probe(monkeypatch) -> None:
    monkeypatch.setattr(
        server._probe,
        "fetch_text",
        lambda *a, **k: '<div class="shopify-section"></div>',
    )
    result = server.probe_platform("https://example.com/products/example-tee")
    assert result["ok"] is True
    assert "shopify" in result["likely_platforms"]
    assert "https://example.com/products/example-tee.js" in result["suggested_fast_paths"]


def test_probe_platform_returns_structured_error(monkeypatch) -> None:
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(server._probe, "fetch_text", boom)
    result = server.probe_platform("https://example.com")
    assert result == {"ok": False, "error": "network down"}


def test_shopify_find_available_uses_collection(monkeypatch) -> None:
    collection = {"products": [FIXTURE]}

    def fake_fetch_json(url, timeout=15):
        assert "collections/mens-tops/products.json" in url
        return collection

    monkeypatch.setattr(server._shopify, "fetch_json", fake_fetch_json)
    result = server.shopify_find_available(
        "https://example.com",
        color="Bright White",
        size="XL",
        need=1,
        collections=["mens-tops"],
    )
    assert result["ok"] is True
    assert result["found"] == 1
    match = result["matches"][0]
    assert match["variant"] == "Bright White / XL"
    assert match["variant_id"] == 102
    assert match["url"] == "https://example.com/products/classic-t-shirt-c-logo-bright-white"


def test_shopify_find_available_skips_unavailable_size(monkeypatch) -> None:
    monkeypatch.setattr(server._shopify, "fetch_json", lambda *a, **k: {"products": [FIXTURE]})
    # 2XL exists in the fixture but is not available -> no match.
    result = server.shopify_find_available(
        "https://example.com",
        color="Bright White",
        size="2XL",
        need=1,
        collections=["mens-tops"],
    )
    assert result["ok"] is True
    assert result["found"] == 0
