# Platform Fast Paths

Use these as cheap probes before falling back to generic page extraction or browser automation.

## General decision order

1. Start from a supplied URL or exact search result.
2. Check if the URL and HTML reveal a known platform.
3. Try the platform's public structured endpoint.
4. Verify exact fields from structured data.
5. Use page extraction for prose, specs, and reviews only after the exact item is identified.
6. Use browser automation only when a task requires JavaScript interaction, auth, or dynamic UI state.

## Shopify

Best for product availability, variants, price, handle, SKU, variant ID.

```text
/products/<handle>.js
/collections/<collection-handle>/products.json?limit=250
/products.json?limit=250
/search/suggest.json?q=<query>&resources[type]=product
/sitemap_products_1.xml
/robots.txt
```

Notes:

- Product `.js` prices are usually integer cents.
- Match exact variant titles. `XL` can appear inside `2XL`, `3XL`, etc.
- Public JSON confirms a current public product state; it does not reserve inventory.
- Some stores disable or restrict broad product-list endpoints.

## WooCommerce

Best for product search, prices, stock status, categories, and images when the Store API is public.

```text
/wp-json/wc/store/v1/products?search=<query>
/wp-json/wc/store/v1/products?slug=<slug>
/wp-json/wp/v2/search?search=<query>
```

Notes:

- Many WooCommerce sites expose Store API read endpoints without auth.
- Do not use add-to-cart endpoints without explicit approval.
- Stock wording can vary by theme/API version.

## WordPress

Best for posts, pages, docs, basic site search, and source discovery.

```text
/wp-json/wp/v2/search?search=<query>
/wp-json/wp/v2/pages?slug=<slug>
/wp-json/wp/v2/posts?slug=<slug>
/wp-sitemap.xml
```

Notes:

- WordPress REST can be disabled or partially blocked.
- For WooCommerce stores, pair WordPress search with Store API products.

## Next.js

Best for pages with server-rendered props or embedded route data.

Look for:

```html
<script id="__NEXT_DATA__" type="application/json">...</script>
```

Notes:

- `__NEXT_DATA__` often contains route props, product data, job descriptions, collection data, or API hints.
- Newer app-router sites may expose less useful route state in HTML. Fall back to JSON-LD and visible extraction when needed.

## Nuxt

Look for:

```text
window.__NUXT__
_payload.json
payload.js
/_nuxt/
```

Notes:

- Nuxt route payloads can carry page data separately from the visible HTML.
- Payload filenames and paths vary by build/deployment.

## Generic JSON-LD

Best for structured facts on unknown platforms.

Look for:

```html
<script type="application/ld+json">...</script>
```

Useful schema types:

```text
Product
Offer
AggregateOffer
Review
BreadcrumbList
FAQPage
Article
JobPosting
Organization
LocalBusiness
```

Notes:

- JSON-LD is often enough for title, SKU, price, currency, availability, rating, posting date, and location.
- Treat JSON-LD as page-owner-provided metadata, not independent verification.

## BigCommerce

Try:

- JSON-LD Product/Offer blocks.
- Embedded theme/context variables.
- Product option JSON in page scripts.
- Storefront API hints when public.

Notes:

- BigCommerce access varies heavily by theme and store config.
- Prefer JSON-LD first unless a clear public endpoint is visible.

## Magento / Adobe Commerce

Try:

- JSON-LD Product/Offer data.
- Swatch/variant JSON in page scripts.
- Configurable product data near `spConfig`, `jsonConfig`, or swatch renderer config.

Avoid:

- Mutating cart/checkout state.
- Reading `window.checkoutConfig` except to understand page structure on cart/checkout pages.

## Fast-path failure modes

- Endpoint returns 404 or HTML instead of JSON.
- Store hides unpublished/out-of-stock products from public lists.
- Product data is app-rendered and not present in first HTML.
- Variant naming differs from user wording.
- Search snippets show a different color or stale stock state.
- Anti-bot systems block automated requests.

When a fast path fails, say what was tried and fall back to extraction or browser with a tighter target.
