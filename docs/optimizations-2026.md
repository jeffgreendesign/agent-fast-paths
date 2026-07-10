# 80/20 Optimizations — agent-fast-paths (July 2026)

A prioritized analysis of the highest-leverage improvements for this project,
with emphasis on **technology changes as of July 2026**. Each item is ranked by
impact ÷ effort — the small set of changes that capture most of the value.

## TL;DR

The repo's *idea* (probe platform-native data surfaces before browsing) is still
correct in 2026 and needs no rethink. What had aged was the **packaging and
tooling** around it:

- It shipped only as a copy-paste skill, while **MCP became the universal way
  agents get tools**. → Ship an MCP server.
- Its toolchain was implied (`.gitignore` lists ruff/mypy caches) but never
  configured, and CI pinned a single, now-old Python. → Adopt **uv + Ruff + ty**,
  test **3.11–3.14**.
- Its Shopify probe didn't anticipate 2026 storefront reality (HTTP 430
  rate-limiting, `.js` sometimes disabled). → Harden it, stdlib-only.

## Priority matrix

| # | Change | Impact | Effort | Kind |
|---|--------|--------|--------|------|
| 1 | **MCP server** exposing the fast paths as tools | High | Med | Technology |
| 2 | **uv + Ruff + ty** toolchain + pre-commit | Med-High | Low | Technology |
| 3 | **CI**: Python 3.11–3.14 matrix, dev branches, uv, lint/type jobs | Med-High | Low | Technology |
| 4 | **Shopify robustness**: 430 retry, `.js`→`.json` fallback, encoding | Med | Med | Correctness |
| 5 | **Content freshness**: official platform MCP servers, GraphQL-only, new frameworks | Med | Low | Docs |
| 6 | **Packaging**: hatchling backend + console entry point | Low-Med | Low | Distribution |

## 1. Expose the fast paths as an MCP server *(headline technology change)*

**Why now.** In 2026 the Model Context Protocol is the industry-standard interface
between agents and tools — adopted across every major AI lab, with 5,000+ servers
and official implementations from Shopify, WooCommerce, GitHub, Stripe, and more.
A project whose entire value is "here's a better way for agents to fetch data" is
strictly more useful when an agent can *call it* than when a human must copy a
script into a sandbox.

**What shipped.** `agent_fast_paths_mcp/` — a `FastMCP` server with three
read-only tools:

- `probe_platform(url)` — platform/endpoint guess.
- `shopify_check_variant(url, variant|options)` — verify one variant, exact option
  equality so `XL` never matches `2XL`/`3XL`/`XLT`.
- `shopify_find_available(base_url, color, size, need)` — the "find N available"
  hunt (collection JSON → sitemap → per-handle `.js`).

It loads the existing example modules **by path** (the same
`importlib.spec_from_file_location` pattern the tests use), so there is a single
source of truth and no logic duplication. It's an **optional extra** (`pip install
.[mcp]`) — the core scripts stay dependency-free.

**Note on official servers.** For a store you own, the official Shopify/WooCommerce
MCP servers are an even faster first-party path. This server is aimed at
third-party public research where you only have the public data surface — that
distinction is now called out in the skill and docs.

## 2. Adopt the modern Python toolchain: uv + Ruff + ty

**Why now.** The Python ecosystem converged in 2026 on the Astral stack: **uv**
(packaging/venv/lockfile, replacing pip/poetry/pyenv), **Ruff** (lint + format,
replacing flake8/black/isort/pyupgrade), and **ty** (type checker, now part of
OpenAI). They're 10–100× faster than the tools they replace and share one
`pyproject.toml`. The repo already anticipated this (its `.gitignore` lists
`.ruff_cache/` and `.mypy_cache/`) but configured nothing.

**What shipped.** `[tool.ruff]`, `[tool.ty]`, a `dev` dependency group, and a
`uv.lock` in `pyproject.toml`, plus a `.pre-commit-config.yaml` running
`ruff` + `ty`. The whole tree now passes `ruff check`, `ruff format --check`, and
`ty check`.

## 3. Modernize CI

**Why now.** CI pinned **Python 3.11 only** and ran **only on `main`** — so a
stdlib change that breaks on 3.12+ ships undetected, and branch work isn't
validated pre-merge. Python **3.14** is the current stable release (3.14.0 was
released Oct 2025; 3.13 is in maintenance).

**What shipped.** A **3.11–3.14 matrix**, triggers on `main` and `claude/**`
branches and all PRs, a switch to **uv with caching**, plus separate `lint`
(ruff + ty) and `mcp` (optional-extra) jobs, keeping the original pytest +
`py_compile` checks.

## 4. Harden the Shopify probe for 2026 reality *(stays stdlib-only)*

**Why now.** Shopify still exposes public product JSON, but the failure modes have
sharpened: it **rate-limits storefront bot traffic with HTTP 430** (also 429/503),
some merchants **disable `.js`**, and new features are **GraphQL-only** (REST is
legacy). The original `fetch_json` did a single naive request.

**What shipped**, all with the standard library only:

- Bounded **retry with backoff** on 429/430/503, honoring `Retry-After`; a clear
  `rate_limited` structured error when exhausted.
- **`.js` → `.json` fallback** (`.json` wraps the product under a `product` key).
- `Accept-Encoding: identity` so a compressing CDN can't hand `urllib` bytes that
  `json.loads` can't parse.

New tests cover the retry-then-success, exhausted-retry, and fallback paths.

## 5. Refresh the platform content

Updated `SKILL.md` and `docs/platform-fast-paths.md` to reflect 2026:

- **Official platform MCP servers** (Shopify, WooCommerce) as the first-party fast
  path; public probes for third-party research.
- Shopify **GraphQL-only** direction and **430** rate-limiting.
- New framework probes: **React Router v7 / Remix** (`window.__remixContext`,
  `<route>.data`), **Astro** islands (`astro-island` props), and the emerging
  **`/llms.txt`** convention.

## 6. Packaging polish

Added a `hatchling` build backend and a `fast-paths-mcp` console entry point so the
server is installable/runnable via `uv`/`uvx`. Kept the example scripts as
copy-paste artifacts (their primary value), so this is additive.

## What was deliberately *not* changed

- **The example scripts stay stdlib-only.** Their value is being pasteable into any
  constrained sandbox; adding `httpx`/`requests` would trade that away for little.
  The MCP server carries the only third-party dependency, isolated in an extra.
- **The core thesis.** Detect → native surface → verify exact field → answer with
  caveats remains correct; no redesign needed.

## Verification

```bash
uv sync --extra mcp --group dev
uv run pytest                     # full suite (incl. MCP + Shopify robustness)
uv run ruff check . && uv run ruff format --check . && uv run ty check
uv run fast-paths-mcp             # starts the MCP server over stdio
```

## Sources (2026)

- Modern Python toolchain (uv + Ruff + ty):
  <https://www.kdnuggets.com/python-project-setup-2026-uv-ruff-ty-polars>,
  <https://blog.rajpoot.dev/posts/python/modern-python-tooling-uv-ruff-2026/>
- MCP as the 2026 standard / official platform servers:
  <https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/>,
  <https://workos.com/blog/everything-your-team-needs-to-know-about-mcp-in-2026>
- Python 3.14 current stable / version status:
  <https://www.python.org/downloads/release/python-3140/>,
  <https://devguide.python.org/versions/>
- Shopify 2026 API direction (GraphQL-only, 430 rate limiting, public products.json):
  <https://tenten.co/shopify/shopify-developer-changelog-api-changes-2026/>,
  <https://shopify.dev/docs/api/usage/limits>
