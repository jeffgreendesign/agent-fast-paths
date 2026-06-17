from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import ModuleType

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "examples" / "platform_probe.py"

spec = importlib.util.spec_from_file_location("platform_probe", MODULE_PATH)
assert spec is not None and spec.loader is not None
probe_mod = importlib.util.module_from_spec(spec)
sys.modules["platform_probe"] = probe_mod
spec.loader.exec_module(probe_mod)
assert isinstance(probe_mod, ModuleType)


def test_probe_detects_shopify_product_url_and_json_ld() -> None:
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {"@context":"https://schema.org", "@type":"Product", "name":"Example Tee"}
        </script>
      </head>
      <body><div class="shopify-section">Example</div></body>
    </html>
    """
    result = probe_mod.probe("https://example.com/products/example-tee", html)
    assert "shopify" in result.likely_platforms
    assert "shopify-or-shopify-like" in result.likely_platforms
    assert "Product" in result.json_ld_types
    assert "https://example.com/products/example-tee.js" in result.suggested_fast_paths


def test_probe_detects_next_data_marker() -> None:
    html = '<script id="__NEXT_DATA__" type="application/json">{"props":{}}</script>'
    result = probe_mod.probe("https://example.com/jobs/123", html)
    assert "nextjs" in result.likely_platforms
    assert any("__NEXT_DATA__" in note for note in result.notes)


def test_probe_strips_existing_shopify_json_suffix() -> None:
    html = '<div class="shopify-section">Example</div>'
    result = probe_mod.probe("https://example.com/products/example-tee.js", html)
    assert "https://example.com/products/example-tee.js" in result.suggested_fast_paths
    assert "https://example.com/products/example-tee.js.js" not in result.suggested_fast_paths
