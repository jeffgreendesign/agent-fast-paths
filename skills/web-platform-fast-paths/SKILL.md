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

As of 2026, some platforms (including Shopify and WooCommerce) ship **official
MCP servers**. When you own the store or have credentials/scope, prefer the
official MCP server — it is the fastest, authenticated fast path. The public
probes in this skill are for third-party research where you only have the public
data surface. This repo also packages these probes as its own MCP server
(`agent_fast_paths_mcp/`) so any MCP client can call them.

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
import json, time, urllib.error, urllib.request

def get_product(base, handle, timeout=15, retries=3):
    # Try /products/<handle>.js, fall back to .json (wrapped under "product"),
    # and back off on Shopify's rate-limit statuses (430/429/503).
    for path in (f'{base}/products/{handle}.js', f'{base}/products/{handle}.json'):
        for attempt in range(retries + 1):
            req = urllib.request.Request(path, headers={
                'User-Agent': 'agent-fast-paths/1.0',
                'Accept-Encoding': 'identity',  # urllib does not decode gzip/br
            })
            try:
                obj = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())
                return obj.get('product', obj)  # .json wraps under "product"
            except urllib.error.HTTPError as e:
                if e.code in (429, 430, 503) and attempt < retries:
                    time.sleep(float(e.headers.get('Retry-After') or 2 ** attempt)); continue
                if e.code in (404, 410):
                    break  # try the next path variant
                raise
    return None

obj = get_product('https://example.com', 'product-handle')
if obj:
    print(obj['title'], obj.get('handle'))
    for v in obj.get('variants', []):
        print(v.get('title'), v.get('available'), v.get('price'), v.get('id'))
PY
```

### Shopify exact-variant hunt, when the user asks for N available products

Use this before browser/page extraction. It should normally solve a task like “find three men’s Bright White shirts in XL” in 2-4 tool calls.

1. Probe the obvious collection endpoint first, but do not linger on guessed collection slugs:
   - Try likely category handles such as `/collections/mens-t-shirt-tops/products.json?limit=250`.
   - If a guessed collection returns empty, immediately use `/sitemap.xml` to discover collection handles instead of trying many guesses.
2. If the collection is broad enough, filter those product objects directly. Shopify collection JSON includes variants, options, tags, and product type.
3. If collection discovery is unclear, use `/sitemap.xml` → `sitemap_products_*.xml?...` and filter product URLs by handle tokens such as `bright-white`, `shirt`, `t-shirt`, `tee`, `polo`, or the requested color/category.
4. Fetch `/products/<handle>.js` only for candidate handles, then stop when you have enough exact available matches.
5. Only crawl `/products.json?limit=250&page=N` when sitemap/collection/search endpoints do not produce enough candidates. If you must crawl it, stop as soon as the requested count is verified.

Copyable exact-match sweep:

```bash
python3 - <<'PY'
import html, json, re, urllib.request
from urllib.parse import urlparse

base = 'https://example.com'
wanted_color = 'Bright White'
wanted_size = 'XL'
need = 3
handle_tokens = ('bright-white', 'shirt', 't-shirt', 'tee', 'polo')
exclude_tokens = ('tank', 'dress', 'bra', 'skort')  # adjust for the requested category

headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json,text/xml,*/*'}

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20).read().decode()

def product_matches(product, handle):
    blob = ' '.join([
        handle,
        product.get('title', ''),
        product.get('product_type', ''),
        ' '.join(product.get('tags', [])),
    ]).lower()
    return any(t in blob for t in handle_tokens) and not any(t in blob for t in exclude_tokens)

def exact_variant(product):
    for v in product.get('variants', []):
        opts = [v.get('option1'), v.get('option2'), v.get('option3')]
        # Prefer option equality over substring matching so XL != 2XL/3XL/XLT.
        if wanted_color in opts and wanted_size in opts:
            return v
    return None

def dollars(price):
    if price is None:
        return None
    # Shopify product JSON may expose cents as int or decimal dollars as a string.
    if isinstance(price, int):
        return price / 100
    s = str(price).strip().replace('$', '').replace(',', '')
    return float(s) if '.' in s else int(s) / 100

handles = []
# 1) Prefer a known collection if you have one.
for coll in ('mens-t-shirt-tops', 'mens-t-shirts-tops', 'mens-shirts'):
    try:
        data = json.loads(get(f'{base}/collections/{coll}/products.json?limit=250'))
    except Exception:
        continue
    for p in data.get('products', []):
        if product_matches(p, p.get('handle', '')) and exact_variant(p):
            handles.append(p['handle'])
    if len(handles) >= need:
        break

# 2) Fall back to sitemap-discovered product handles, not page extraction.
if len(handles) < need:
    sm = get(f'{base}/sitemap.xml')
    product_maps = re.findall(r'<loc>([^<]*sitemap_products_[^<]+)</loc>', sm)
    for sm_url in product_maps:
        text = get(html.unescape(sm_url))
        urls = re.findall(r'<loc>(https?://[^<]+/products/[^<]+)</loc>', text)
        for u in urls:
            h = urlparse(html.unescape(u)).path.rsplit('/products/', 1)[-1]
            if all(t not in h for t in handle_tokens):
                continue
            handles.append(h)

seen = set()
for h in handles:
    if h in seen:
        continue
    seen.add(h)
    try:
        product = json.loads(get(f'{base}/products/{h}.js'))
    except Exception:
        continue
    variant = exact_variant(product)
    if product_matches(product, h) and variant and variant.get('available') is True:
        print(json.dumps({
            'product': product.get('title'),
            'url': f'{base}/products/{h}',
            'variant': variant.get('title'),
            'available': variant.get('available'),
            'price': dollars(variant.get('price')),
            'variant_id': variant.get('id'),
        }, sort_keys=True))
        need -= 1
        if need == 0:
            break
PY
```

Variant filtering example for an already-fetched product:

```python
wanted_color = 'Bright White'
wanted_size = 'XL'
for v in obj['variants']:
    opts = [v.get('option1'), v.get('option2'), v.get('option3')]
    if wanted_color in opts and wanted_size in opts:
        print(v['title'], v['available'], v['price'])
```

Collection sweep example:

```bash
python3 - <<'PY'
import json, urllib.request
url='https://example.com/collections/mens-t-shirt-tops/products.json?limit=250'
data=json.loads(urllib.request.urlopen(url,timeout=20).read().decode())
for p in data.get('products', []):
    blob = ' '.join([p.get('title',''), p.get('product_type',''), ' '.join(p.get('tags', []))]).lower()
    if 'shirt' in blob or 'tee' in blob or 'polo' in blob:
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

2026 notes:

- If `.js` is disabled (404/410), fall back to `/products/<handle>.json` (same data under a `product` key).
- Shopify rate-limits bot traffic with **HTTP 430** (also 429/503); back off and honor `Retry-After`.
- New Shopify features are **GraphQL-only**; the public REST/`.js`/`.json` reads still work but are legacy — verify exact fields.
- Send `Accept-Encoding: identity` since `urllib` will not decode gzip/brotli.

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

### React Router / Remix

Remix merged into React Router v7 and is common on 2026 commerce/content sites. Look for:

- `window.__remixContext` — loader data embedded in the HTML.
- `<route-url>.data` — single-fetch route data (append `.data` to a route URL).

Shapes vary by version/single-fetch config; treat as probes, not guarantees.

### Astro

Astro renders mostly static HTML with hydrated islands. Prefer JSON-LD/Open Graph first (usually present), then inspect `astro-island` elements whose `props` attribute carries JSON state.

### llms.txt

Some sites publish an agent-friendly content map at `/llms.txt` (and sometimes `/llms-full.txt`). When present it can point straight at canonical docs/product URLs, saving a discovery pass. Check cheaply; adoption is uneven.

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

5. **Over-probing broad catalogs.** For a quick user request, find enough exact options. Do not crawl the whole store unless asked. Prefer collection JSON and sitemap-discovered product handles before `/products.json?page=N` pagination.

6. **Lingering on guessed collection slugs.** One miss is useful signal; many misses waste time. If `/collections/<guess>/products.json` is empty, inspect `/sitemap.xml` for real collection handles such as `mens-t-shirt-tops`.

7. **Ignoring side-effect boundaries.** Reading public JSON is fine. Adding to cart, reserving inventory, logging in, or buying requires explicit approval.

8. **Assuming all Shopify stores expose all products.** Some disable endpoints, hide products, paginate aggressively, or rely on apps. Fall back to JSON-LD, sitemap, search suggest, or browser.

## Verification Checklist

- [ ] Platform or likely platform identified.
- [ ] Fast endpoint attempted before slow extraction/browser, unless user provided already-structured data.
- [ ] Exact product/variant/field verified from structured data.
- [ ] Price units converted with a tool when needed.
- [ ] Availability caveat stated if stock matters.
- [ ] Side-effect actions avoided unless explicitly approved.
