# Post Draft: Agent Fast Paths Beat Generic Browsing

A small Hermes Agent lesson from a simple shopping task:

I asked for three white Champion men’s shirts available in XL. The agent found them, but it took the scenic route: search results, page extraction, then finally the thing it should have tried first.

Champion runs on Shopify, so the fast path is public product JSON:

```text
/products/<handle>.js
```

That endpoint gives the useful agent facts directly: title, handle, variants, availability, price, and variant IDs.

For this task, the whole workflow should have been:

1. Find candidate product URLs.
2. Fetch each `/products/<handle>.js` endpoint.
3. Filter variants for `Bright White / XL` and `available: true`.
4. Return the verified links and prices.

The correction became a reusable Hermes skill: **web-platform-fast-paths**.

The broader pattern is the useful part. Agents should not treat every web page as opaque. A lot of sites expose structured surfaces:

- Shopify product and collection JSON
- WooCommerce Store API
- WordPress REST endpoints
- Next.js `__NEXT_DATA__`
- Nuxt payload files
- JSON-LD Product / Offer / JobPosting data

Good agent behavior is not “browse harder.” It is:

> Detect the platform, use the native data surface, verify the exact field, then answer with caveats.

This makes the agent faster, cheaper, and less likely to hallucinate stock, prices, or variant availability from stale snippets.

Tiny example:

```python
import json, urllib.request

url = "https://www.champion.com/products/champion-classic-t-shirt-c-logo-bright-white.js"
product = json.loads(urllib.request.urlopen(url, timeout=15).read().decode())

for variant in product["variants"]:
    if variant["title"] == "Bright White / XL":
        print(variant["available"], variant["price"] / 100)
```

The point is not Shopify trivia. It is agent UX: reusable procedures turn corrections into better future behavior.

## Compact version

Small Hermes lesson: agents need platform fast paths, not just generic browsing.

I asked for three white Champion men’s shirts in XL. The agent got the answer, but wasted steps with search + page extraction before using the obvious Shopify route:

```text
/products/<handle>.js
```

That gives structured product data: variants, availability, prices, IDs.

So I saved the correction as a Hermes skill: **web-platform-fast-paths**.

Pattern:

1. Detect the platform.
2. Use the native data endpoint.
3. Verify the exact field.
4. Answer with caveats.

Shopify has product JSON. WooCommerce has Store API. WordPress has REST. Next.js has `__NEXT_DATA__`. Many sites already expose the facts agents need.

Better agent behavior is often just remembering the boring shortcut.
