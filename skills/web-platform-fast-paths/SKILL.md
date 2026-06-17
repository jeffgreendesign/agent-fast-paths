---
name: web-platform-fast-paths
description: Use when researching products, listings, availability, prices, docs, or page facts on sites that may expose machine-readable platform endpoints such as Shopify, WooCommerce, BigCommerce, Magento, WordPress, Next.js, Nuxt, or static-site data manifests. Prefer framework-native JSON/data endpoints before slow visual browsing or generic page extraction.
version: 1.0.0
author: Jeff Green
license: MIT
metadata:
  hermes:
    tags: [web-research, shopping, shopify, ecommerce, platform-detection, agent-fast-paths]
    related_skills: [shopping-product-comparison, research-source-operations]
---

# Web Platform Fast Paths

## Overview

Many web research tasks are slow only because the agent treats every site as an opaque web page. Modern commerce and framework sites often expose structured data that is faster, cleaner, and more reliable than rendered HTML.

Use this skill to check framework-native endpoints first, then fall back to page extraction or browser automation only when needed.

Core principle:

> Detect the platform, use its public data surface, verify the specific variant/fact, then answer concisely with caveats.

## When to Use

Use when the user asks for:
- Product availability, size/color variants, prices, SKUs, handles, collection listings, or recommendations.
- Retail/ecommerce research on Shopify, WooCommerce, BigCommerce, Magento/Adobe Commerce, Salesforce Commerce Cloud, or similar stores.
- Current facts from a modern web app where the page likely has embedded JSON state.
- A task that seems like browsing but may have predictable JSON endpoints.
- "This should be quick; it's on Shopify" style corrections.

Do not use for:
- Private/authenticated account state unless the user explicitly provides access and scope.
- Checkout, cart mutation, buying, posting, or other side-effect actions without explicit approval.
- Sites where terms, robots, or auth boundaries clearly block automated access. Use normal web/browser methods and say what is blocked.

## Fast Sequence

1. **Find candidate URLs**
   - Use web search for exact product/title/domain searches.
   - If the user gives a URL, start there.
   - Do not trust search snippets for stock, price, or variants.

2. **Probe platform-native endpoints**
   - Shopify product: `/products/<handle>.js`
   - Shopify collection: `/collections/<collection-handle>/products.json?limit=250`
   - Shopify all products: `/products.json?limit=250` when appropriate and not too broad.
   - WooCommerce: `/wp-json/wc/store/v1/products?search=<term>`
   - WordPress posts/pages: `/wp-json/wp/v2/search?search=<term>`
   - Next.js: inspect page HTML for `__NEXT_DATA__` script JSON.
   - Nuxt: inspect `window.__NUXT__`, `payload.js`, or `_payload.json` references.
   - Generic product pages: inspect JSON-LD `application/ld+json` for `Product`, `Offer`, `availability`, `sku`, `price`, and variants.

3. **Verify exact fields**
   - Product title/handle.
   - Color/size/variant title.
   - `available` / stock flag.
   - Price in cents vs dollars. Shopify `.js` prices are usually integer cents.
   - Variant ID/SKU only if relevant.
   - Review count/rating only if needed for the decision.

4. **Answer from verified facts**
   - State the exact variant checked, e.g. `Bright White / XL`.
   - Include direct product links.
   - Mention if price/stock may change.
   - Do not overexplain the scraping unless the user asks or experience quality matters.

## Shopify Quick Path

For Shopify, prefer this pattern before page extraction:

```bash
python3 - <<'PY'
import json, urllib.request
urls = [
  'https://example.com/products/product-handle.js',
]
for url in urls:
    obj = json.loads(urllib.request.urlopen(url, timeout=15).read().decode())
    print(obj['title'], obj.get('handle'))
    for v in obj.get('variants', []):
        print(v.get('title'), v.get('available'), v.get('price'), v.get('id'))
PY
```

Variant filtering example:

```python
wanted_color = 'Bright White'
wanted_size = 'XL'
for v in obj['variants']:
    title = v.get('title', '')
    exact_size = title.endswith(f'/ {wanted_size}') or f'/ {wanted_size} /' in title
    if wanted_color in title and exact_size:
        print(title, v['available'], v['price'] / 100)
```

Collection sweep example:

```bash
python3 - <<'PY'
import json, urllib.request
url='https://example.com/collections/mens-t-shirts/products.json?limit=250'
data=json.loads(urllib.request.urlopen(url,timeout=20).read().decode())
for p in data.get('products', []):
    if 'shirt' in p.get('title','').lower():
        print(p['title'], p['handle'])
PY
```

### Shopify endpoints worth trying

- `/products/<handle>.js` — product JSON with variants and prices.
- `/products.json?limit=250` — product list; may be blocked, paginated, or incomplete.
- `/collections/<handle>/products.json?limit=250` — collection-scoped product list.
- `/search/suggest.json?q=<query>&resources[type]=product` — predictive search, when enabled.
- `/sitemap_products_1.xml` — product URL discovery.
- `/robots.txt` — sitemap hints and crawl boundaries.

## Other Platform Hints

### WooCommerce / WordPress

Try public Store API first:

```text
/wp-json/wc/store/v1/products?search=<query>
/wp-json/wc/store/v1/products?slug=<slug>
/wp-json/wp/v2/search?search=<query>
```

The Store API may expose prices, stock status, images, categories, and add-to-cart data without admin credentials. Treat availability fields as current but still changeable.

### BigCommerce

BigCommerce storefronts often expose product data through page JSON or GraphQL-backed storefront APIs, but access varies by theme and headers. Look for:

- JSON-LD Product/Offer blocks.
- `stencil` / `context` variables in HTML.
- Embedded product ID and variant option data.
- Storefront API references, if public.

### Magento / Adobe Commerce

Look for:

- JSON-LD Product/Offer data.
- `window.checkoutConfig` only on cart/checkout pages; do not mutate cart.
- Swatch/variant JSON in page scripts.
- Product configurable option JSON near `spConfig` or `jsonConfig`.

### Next.js

Fetch the page HTML and extract:

```text
<script id="__NEXT_DATA__" type="application/json">...</script>
```

This often contains props, product data, collection data, or API route hints. If data is not in `__NEXT_DATA__`, inspect script URLs under `/_next/static/` for build IDs and route chunks, but do not spend too long reverse-engineering a site unless the task warrants it.

### Nuxt

Look for:

- `window.__NUXT__`
- `_payload.json`
- `payload.js`
- `/_nuxt/` route data references

### Generic structured data

If platform-specific endpoints fail, inspect JSON-LD:

```text
<script type="application/ld+json">...</script>
```

Useful types: `Product`, `Offer`, `AggregateOffer`, `Review`, `BreadcrumbList`, `FAQPage`, `Article`, `JobPosting`.

## Tool Choice

Prefer:
- Shell/Python probes for small JSON checks.
- Web search for candidate discovery.
- Page extraction for prose/spec sections once the exact product/page is identified.
- Browser automation only when JavaScript interaction, auth, or anti-bot rendering makes it necessary.

Avoid:
- Starting with screenshots or visual browsing for public product data.
- Treating summarized page extraction as stock verification.
- Doing arithmetic mentally. Use a tool for price conversions or per-unit calculations.

## Output Pattern

For quick shopping/product tasks:

```markdown
Found and verified via <platform> product data:

1. **Product name**
   - Variant checked: Color / XL
   - Availability: available
   - Price: $X.XX
   - Link: ...

Caveat: stock/prices can change. I checked public product JSON, not checkout inventory reservation.
```

For agent-experience feedback:

```markdown
Should have been <N> calls:
1. Search/find handle or use supplied URL.
2. Hit platform JSON endpoint and filter variants.

What went wrong: <specific detour>.
Fix saved: use `web-platform-fast-paths` for future product/platform lookups.
```

## Common Pitfalls

1. **Using page extraction first on Shopify.** It can summarize marketing/reviews but may omit the exact variant matrix. Use `.js` product JSON first.

2. **Confusing XL with 2XL/3XL.** Match exact size tokens. In variant titles, `XL` may also appear inside `2XL`; exclude larger sizes unless requested.

3. **Trusting snippets for stock.** Search results can be stale or show another color/variant.

4. **Forgetting cents.** Shopify product JSON usually stores price as cents, e.g. `1875` = `$18.75`.

5. **Over-probing broad catalogs.** For a quick user request, find enough exact options. Do not crawl the whole store unless asked.

6. **Ignoring side-effect boundaries.** Reading public JSON is fine. Adding to cart, reserving inventory, logging in, or buying requires explicit approval.

7. **Assuming all Shopify stores expose all products.** Some disable endpoints, hide products, paginate aggressively, or rely on apps. Fall back to JSON-LD, sitemap, search suggest, or browser.

## Verification Checklist

- [ ] Platform or likely platform identified.
- [ ] Fast endpoint attempted before slow extraction/browser, unless user provided already-structured data.
- [ ] Exact product/variant/field verified from structured data.
- [ ] Price units converted with a tool when needed.
- [ ] Availability caveat stated if stock matters.
- [ ] Side-effect actions avoided unless explicitly approved.
