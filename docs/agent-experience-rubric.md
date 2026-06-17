# Agent Experience Rubric

Use this quick rubric when a task technically succeeded but the path felt too slow, tool-heavy, or fragile.

Score each category 0-2 for a 10-point total.

| Category | 0 | 1 | 2 |
|---|---|---|---|
| Correctness | Wrong or unverified answer | Mostly right, weak caveats | Verified exact answer |
| Fast-path choice | Generic browsing despite obvious structured data | Fast path used late | Platform-native endpoint tried early |
| Tool economy | Many avoidable calls | Some detours | Minimal calls for the evidence needed |
| Field precision | Fuzzy/snippet-level facts | Exact page but weak variant/date/price check | Exact field/variant/date/price verified |
| Boundary handling | Side effects or private/auth risk | Boundary implied | Read-only scope and caveats explicit |

## Example: Shopify product availability

A good answer should:

- identify exact product URLs or handles
- use `/products/<handle>.js`
- match exact variant names such as `Bright White / XL`
- avoid matching `2XL` or `3XL` when the user asked for `XL`
- convert price cents with a tool or code
- state that public stock/prices can change

## Rating language

```text
Result quality: good / mixed / poor
Speed/path efficiency: good / mediocre / poor
Verification: exact / partial / unverified
Overall: N/10
Main correction: <one sentence>
```

## What to save as a skill

Save a reusable skill when the correction is procedural and likely to recur:

- platform endpoint patterns
- exact CLI/API commands
- extraction pitfalls
- side-effect boundaries
- verification checklist

Do not save one-off product results, prices, PR numbers, or transient stock data as memory.
