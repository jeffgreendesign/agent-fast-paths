from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

pytest.importorskip("mcp", reason="MCP extra not installed")

from agent_fast_paths_mcp import server  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "shopify_product.json").read_text())

# Capture the real SSRF guard before the autouse fixture stubs it out, so the
# guard's own tests can exercise it without touching the network.
_real_assert_fetchable = server._assert_fetchable


@pytest.fixture(autouse=True)
def _bypass_ssrf_guard(monkeypatch):
    # Tool-behavior tests fetch mocked data; skip the guard's real DNS lookups.
    monkeypatch.setattr(server, "_assert_fetchable", lambda *a, **k: None)


def _addrinfo(ip: str):
    return [(2, 1, 6, "", (ip, 80))]


def test_ssrf_guard_rejects_non_http_scheme() -> None:
    with pytest.raises(server.BlockedURLError, match="scheme"):
        _real_assert_fetchable("file:///etc/passwd")


def test_ssrf_guard_blocks_loopback(monkeypatch) -> None:
    monkeypatch.setattr(server.socket, "getaddrinfo", lambda *a, **k: _addrinfo("127.0.0.1"))
    with pytest.raises(server.BlockedURLError, match="non-public"):
        _real_assert_fetchable("http://localhost/admin")


def test_ssrf_guard_blocks_cloud_metadata(monkeypatch) -> None:
    monkeypatch.setattr(server.socket, "getaddrinfo", lambda *a, **k: _addrinfo("169.254.169.254"))
    with pytest.raises(server.BlockedURLError, match="non-public"):
        _real_assert_fetchable("http://metadata.internal/latest/meta-data/")


def test_ssrf_guard_blocks_private_range(monkeypatch) -> None:
    monkeypatch.setattr(server.socket, "getaddrinfo", lambda *a, **k: _addrinfo("10.0.0.5"))
    with pytest.raises(server.BlockedURLError, match="non-public"):
        _real_assert_fetchable("https://intranet.example/")


def test_ssrf_guard_allows_public_address(monkeypatch) -> None:
    monkeypatch.setattr(server.socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    # Should not raise.
    _real_assert_fetchable("https://example.com/products/x.js")


def test_ssrf_guard_allow_local_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(server, "_ALLOW_LOCAL", True)
    # With the opt-in set, loopback is permitted and DNS is not even consulted.
    _real_assert_fetchable("http://127.0.0.1:9292/products/x.js")


def test_probe_platform_blocks_private_url(monkeypatch) -> None:
    # Restore the real guard (autouse stubbed it) and exercise it through a tool.
    # A numeric IP host needs no DNS, so this stays offline.
    monkeypatch.setattr(server, "_assert_fetchable", _real_assert_fetchable)
    result = server.probe_platform("http://169.254.169.254/latest/meta-data/")
    assert result["ok"] is False
    assert "blocked_url" in result["error"]


def test_tools_are_registered() -> None:
    # Use FastMCP's public (async) tool-listing API rather than private internals.
    tools = asyncio.run(server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert {"probe_platform", "shopify_check_variant", "shopify_find_available"} <= names


def test_shopify_check_variant_matches_xl_not_2xl(monkeypatch) -> None:
    monkeypatch.setattr(server._shopify, "fetch_product", lambda url, **k: (FIXTURE, url))
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


def test_shopify_check_variant_reports_served_url_on_fallback(monkeypatch) -> None:
    # fetch_product reports the .json URL when the .js view was disabled.
    json_url = "https://example.com/products/classic-t-shirt.json"
    monkeypatch.setattr(server._shopify, "fetch_product", lambda *a, **k: (FIXTURE, json_url))
    result = server.shopify_check_variant(
        "https://example.com/products/classic-t-shirt",
        options=["Bright White", "XL"],
    )
    assert result["ok"] is True
    assert result["source_url"] == json_url


def test_shopify_check_variant_reports_missing_variant(monkeypatch) -> None:
    monkeypatch.setattr(server._shopify, "fetch_product", lambda url, **k: (FIXTURE, url))
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
