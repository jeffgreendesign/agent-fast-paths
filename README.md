# Agent Fast Paths

Reusable fast paths for AI agents that research public web pages.

The core idea is simple: agents should not treat every page as opaque HTML. Many sites expose structured public data surfaces that are faster, cheaper, and more reliable than visual browsing or generic page summarization.

> Detect the platform, use the native data surface, verify the exact field, then answer with caveats.

## Why this exists

A small shopping lookup exposed a common agent failure mode: the agent searched and summarized pages before using the obvious Shopify product JSON endpoint.

For Shopify products, this is often enough:

```text
/products/<handle>.js
```

That endpoint can expose product title, handle, variants, availability, price, SKU, and variant IDs.

This repo packages that correction as a reusable Hermes Agent skill plus small examples agents can copy.

## What's included

```text
skills/web-platform-fast-paths/SKILL.md   Hermes skill
examples/shopify_variant_check.py         Shopify product variant checker
examples/platform_probe.py                Lightweight platform probe helper
docs/platform-fast-paths.md               Endpoint patterns by platform
docs/agent-experience-rubric.md           Quick rubric for rating agent behavior
```

## Supported fast paths

| Platform / pattern | Useful public surfaces |
|---|---|
| Shopify | `/products/<handle>.js`, `/collections/<handle>/products.json`, `/products.json`, search suggest, sitemaps |
| WooCommerce | `/wp-json/wc/store/v1/products`, WordPress REST search |
| WordPress | `/wp-json/wp/v2/search`, JSON-LD, page/post REST data |
| Next.js | `__NEXT_DATA__` script JSON |
| Nuxt | `window.__NUXT__`, `_payload.json`, `payload.js` |
| Generic product pages | JSON-LD `Product`, `Offer`, `AggregateOffer`, `Review` |
| Job/document pages | JSON-LD `JobPosting`, `Article`, `FAQPage` |
| BigCommerce / Magento | JSON-LD and embedded product/variant config where exposed |

Shopify is the most deterministic path here. Others are probes, not guarantees.

## Quick Shopify example

```bash
python3 examples/shopify_variant_check.py \
  'https://www.champion.com/products/champion-classic-t-shirt-c-logo-bright-white' \
  --variant 'Bright White / XL'
```

Output shape:

```json
{
  "product": "Classic T-Shirt, C Logo",
  "handle": "champion-classic-t-shirt-c-logo-bright-white",
  "variant": "Bright White / XL",
  "available": true,
  "price": 15.0,
  "price_cents": 1500
}
```

Stock and prices can change. Treat product JSON as a public current read, not an inventory reservation.

## Install the Hermes skill locally

Copy or symlink the skill directory into your Hermes skills folder:

```bash
mkdir -p ~/.hermes/skills/research
cp -R skills/web-platform-fast-paths ~/.hermes/skills/research/
```

Then start a new Hermes session or reload skills, depending on your setup.

## Agent behavior rule

Before browser automation or broad page extraction, try this order:

1. Use a supplied URL or find exact candidate URLs.
2. Detect the platform from URL patterns, headers, HTML markers, or known endpoints.
3. Probe platform-native structured endpoints.
4. Verify exact fields, especially variant names, stock flags, price units, and dates.
5. Fall back to extraction/browser only when structured data is missing or insufficient.
6. State caveats when data is volatile or endpoint support is partial.

## Side-effect boundary

This repo is for public read-only research. Do not use these patterns to add items to carts, reserve inventory, log in, mutate checkout state, scrape private account data, or bypass access controls.

## License

MIT
