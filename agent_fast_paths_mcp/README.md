# agent-fast-paths MCP server

Exposes the web-platform fast paths as [Model Context Protocol](https://modelcontextprotocol.io)
tools so any MCP-compatible agent can call them directly, instead of copy-pasting
the example scripts. As of 2026 MCP is the universal standard for connecting
agents to tools, so this is the widest-reach way to ship these fast paths.

The server is a thin wrapper over the stdlib-only example modules in
[`../examples/`](../examples/) (loaded by path — single source of truth, no logic
duplicated). It is strictly **read-only**: no cart, checkout, auth, or any
state-changing endpoint.

## Tools

| Tool | Purpose |
| --- | --- |
| `probe_platform(url)` | Guess a page's platform and suggest structured-data endpoints (Shopify, WooCommerce/WordPress, Next.js, Nuxt, JSON-LD). |
| `shopify_check_variant(url, variant?, options?)` | Verify one Shopify variant via the public product JSON. Exact option equality, so `XL` never matches `2XL`/`3XL`/`XLT`. Returns availability + price in dollars and cents. |
| `shopify_find_available(base_url, color, size, need=3, collections?)` | Find N products available in an exact color + size via collection JSON → sitemap discovery → per-handle `.js`. |

## Run it

From a repo checkout (the server loads the example modules relative to the repo
root; set `AGENT_FAST_PATHS_EXAMPLES` to override that location):

```bash
uv sync --extra mcp
uv run fast-paths-mcp          # serves over stdio
# or, without cloning into your project:
uvx --from . fast-paths-mcp
```

## Register with an MCP client

Add to your client's MCP server config (e.g. `claude_desktop_config.json` or a
Claude Code `.mcp.json`):

```json
{
  "mcpServers": {
    "agent-fast-paths": {
      "command": "uv",
      "args": ["run", "--extra", "mcp", "fast-paths-mcp"],
      "cwd": "/absolute/path/to/agent-fast-paths"
    }
  }
}
```

## Security: SSRF guard and trust model

The tools fetch agent-supplied URLs, so each request is validated first: only
`http(s)` is allowed, and the host must resolve to a **public** address. Requests
to loopback, RFC1918/private, link-local (including the cloud-metadata endpoint
`169.254.169.254`), reserved, multicast, or unspecified addresses are rejected
with a `blocked_url` error. Sitemap-index entries are re-validated before they
are fetched.

Caveat: the guard checks the URL you pass; it does **not** re-validate HTTP
redirect hops (urllib follows those internally). Treat this server as
**trusted-caller only** — don't expose it to fully untrusted input where a
redirect-based SSRF would matter.

To allow localhost/private hosts for local development (e.g. a dev store on
`127.0.0.1`), set `AGENT_FAST_PATHS_ALLOW_LOCAL=1` in the server's environment.

## First-party alternative

For your own store, Shopify and WooCommerce now ship official MCP servers with
authenticated, first-party access — prefer those when you own the store. This
server targets **public, third-party research** where you only have the public
data surface.
