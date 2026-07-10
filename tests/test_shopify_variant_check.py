from __future__ import annotations

import email.message
import importlib.util
import io
import json
import pathlib
import sys
import urllib.error
from types import ModuleType

import pytest

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


def test_find_variant_by_options_rejects_ambiguous_partial_options() -> None:
    product = {
        "variants": [
            {"id": 1, "title": "Bright White / XL"},
            {"id": 2, "title": "Black / XL"},
        ]
    }
    with pytest.raises(svc.VariantNotFoundError, match="ambiguous option match"):
        svc.find_variant_by_options(product, ["XL"])


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
    code = svc.main(
        ["https://example.com/products/classic-t-shirt", "--variant", "Bright White / XL"]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is True
    assert out["price"] == 15.0


def test_cli_outputs_option_match_json(capsys, monkeypatch) -> None:
    monkeypatch.setattr(svc, "fetch_json", lambda *args, **kwargs: FIXTURE)
    code = svc.main(
        [
            "https://example.com/products/classic-t-shirt",
            "--option",
            "Bright White",
            "--option",
            "XL",
        ]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["variant"] == "Bright White / XL"
    assert out["available"] is True


def test_cli_rejects_variant_and_option_together(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        svc,
        "fetch_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fetch_json should not be called")
        ),
    )
    with pytest.raises(SystemExit) as exc:
        svc.main(
            [
                "https://example.com/products/classic-t-shirt",
                "--variant",
                "Bright White / XL",
                "--option",
                "Bright White",
            ]
        )
    assert exc.value.code != 0
    assert "provide exactly one of --variant or repeatable --option" in capsys.readouterr().err


def test_cli_rejects_missing_selection_mode(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        svc,
        "fetch_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fetch_json should not be called")
        ),
    )
    with pytest.raises(SystemExit) as exc:
        svc.main(["https://example.com/products/classic-t-shirt"])
    assert exc.value.code != 0
    assert "provide exactly one of --variant or repeatable --option" in capsys.readouterr().err


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self, *args: object) -> bytes:
        return self._buf.read()


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.com", code, "err", hdrs, None)


def test_fetch_json_retries_on_rate_limit_then_succeeds(monkeypatch) -> None:
    calls = {"n": 0}
    payload = json.dumps({"title": "ok"}).encode("utf-8")

    def fake_urlopen(request, timeout=15):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(430, retry_after="2")
        return _FakeResponse(payload)

    sleeps: list[float] = []
    monkeypatch.setattr(svc.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(svc.time, "sleep", lambda seconds: sleeps.append(seconds))

    # backoff=0.0 means any non-zero sleep must come from the Retry-After header.
    result = svc.fetch_json("https://example.com/products/x.js", backoff=0.0)
    assert result == {"title": "ok"}
    assert calls["n"] == 3
    assert sleeps == [2.0, 2.0]


def test_retry_after_is_bounded_and_validated() -> None:
    assert svc._retry_after_seconds(_http_error(430, retry_after="5")) == 5.0
    # Oversized values are capped, invalid/negative/non-finite fall back to None.
    assert svc._retry_after_seconds(_http_error(430, retry_after="99999")) == svc.MAX_RETRY_AFTER
    assert svc._retry_after_seconds(_http_error(430, retry_after="-3")) is None
    assert svc._retry_after_seconds(_http_error(430, retry_after="inf")) is None
    assert svc._retry_after_seconds(_http_error(430, retry_after="nope")) is None
    assert svc._retry_after_seconds(_http_error(430)) is None


def test_fetch_json_rejects_non_object_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        svc.urllib.request,
        "urlopen",
        lambda *a, **k: _FakeResponse(b'["not", "an", "object"]'),
    )
    with pytest.raises(ValueError, match="expected a JSON object"):
        svc.fetch_json("https://example.com/products/x.js")


def test_fetch_json_raises_rate_limited_when_exhausted(monkeypatch) -> None:
    monkeypatch.setattr(
        svc.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(_http_error(430))
    )
    monkeypatch.setattr(svc.time, "sleep", lambda _seconds: None)

    with pytest.raises(svc.RateLimitedError, match="rate_limited"):
        svc.fetch_json("https://example.com/products/x.js", retries=2, backoff=0.0)


def test_fetch_product_falls_back_from_js_to_json(monkeypatch) -> None:
    def fake_fetch_json(url, timeout=15):  # noqa: ARG001
        if url.endswith(".js"):
            raise _http_error(404)
        return {"product": FIXTURE}

    monkeypatch.setattr(svc, "fetch_json", fake_fetch_json)
    product, source_url = svc.fetch_product("https://example.com/products/classic-t-shirt.js")
    assert product["title"] == FIXTURE["title"]
    assert source_url == "https://example.com/products/classic-t-shirt.json"
    variant = svc.find_variant(product, "Bright White / XL")
    assert variant["id"] == 102


def test_fetch_product_propagates_non_404_errors(monkeypatch) -> None:
    monkeypatch.setattr(svc, "fetch_json", lambda *a, **k: (_ for _ in ()).throw(_http_error(500)))
    with pytest.raises(urllib.error.HTTPError):
        svc.fetch_product("https://example.com/products/x.js")
