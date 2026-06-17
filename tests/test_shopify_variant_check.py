from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from types import ModuleType

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "examples" / "shopify_variant_check.py"

spec = importlib.util.spec_from_file_location("shopify_variant_check", MODULE_PATH)
assert spec is not None and spec.loader is not None
svc = importlib.util.module_from_spec(spec)
sys.modules["shopify_variant_check"] = svc
spec.loader.exec_module(svc)
assert isinstance(svc, ModuleType)

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "shopify_product.json").read_text())


def test_product_json_url_from_product_page() -> None:
    assert (
        svc.product_json_url("https://example.com/products/classic-t-shirt?variant=123")
        == "https://example.com/products/classic-t-shirt.js"
    )


def test_product_json_url_keeps_existing_json_url() -> None:
    assert (
        svc.product_json_url("https://example.com/products/classic-t-shirt.js?utm_source=x")
        == "https://example.com/products/classic-t-shirt.js"
    )


def test_find_variant_matches_exact_xl_not_2xl() -> None:
    variant = svc.find_variant(FIXTURE, "Bright White / XL")
    assert variant["id"] == 102
    assert variant["title"] != "Bright White / 2XL"


def test_find_variant_by_options_matches_exact_xl_not_2xl() -> None:
    variant = svc.find_variant_by_options(FIXTURE, ["Bright White", "XL"])
    assert variant["id"] == 102
    assert variant["title"] == "Bright White / XL"


def test_find_variant_by_options_ignores_option_order() -> None:
    variant = svc.find_variant_by_options(FIXTURE, ["XL", "Bright White"])
    assert variant["id"] == 102


def test_summarize_variant_converts_cents() -> None:
    variant = svc.find_variant(FIXTURE, "Bright White / XL")
    summary = svc.summarize_variant(FIXTURE, variant, "https://example.com/products/x.js")
    assert summary == {
        "product": "Classic T-Shirt, C Logo",
        "handle": "classic-t-shirt-c-logo-bright-white",
        "source_url": "https://example.com/products/x.js",
        "variant": "Bright White / XL",
        "available": True,
        "price": 15.0,
        "price_cents": 1500,
        "variant_id": 102,
        "sku": "TEE-WHT-XL",
    }


def test_cli_outputs_variant_json(capsys, monkeypatch) -> None:
    monkeypatch.setattr(svc, "fetch_json", lambda *args, **kwargs: FIXTURE)
    code = svc.main(["https://example.com/products/classic-t-shirt", "--variant", "Bright White / XL"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is True
    assert out["price"] == 15.0


def test_cli_outputs_option_match_json(capsys, monkeypatch) -> None:
    monkeypatch.setattr(svc, "fetch_json", lambda *args, **kwargs: FIXTURE)
    code = svc.main([
        "https://example.com/products/classic-t-shirt",
        "--option",
        "Bright White",
        "--option",
        "XL",
    ])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["variant"] == "Bright White / XL"
    assert out["available"] is True
