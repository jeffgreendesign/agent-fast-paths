"""MCP server that exposes the agent-fast-paths web research fast paths."""

from __future__ import annotations

__all__ = ["main"]


def main() -> None:
    from .server import main as _main

    _main()
