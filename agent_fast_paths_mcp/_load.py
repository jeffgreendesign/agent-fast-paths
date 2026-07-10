"""Load the stdlib-only example modules by path.

The example scripts in ``examples/`` are deliberately not a package (so they
stay copy-paste-anywhere). This mirrors the ``importlib.util.spec_from_file_location``
pattern used by the test suite, giving the MCP server a single source of truth
for the fast-path logic with no duplication.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
from types import ModuleType


def _examples_dir() -> pathlib.Path:
    override = os.environ.get("AGENT_FAST_PATHS_EXAMPLES")
    if override:
        return pathlib.Path(override).expanduser().resolve()
    # agent_fast_paths_mcp/_load.py -> repo root is one parent up.
    return pathlib.Path(__file__).resolve().parents[1] / "examples"


def _load(module_name: str, filename: str) -> ModuleType:
    path = _examples_dir() / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"Could not find {filename} at {path}. Run the MCP server from a repo "
            "checkout, or set AGENT_FAST_PATHS_EXAMPLES to the examples directory."
        )
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


shopify = _load("shopify_variant_check", "shopify_variant_check.py")
probe = _load("platform_probe", "platform_probe.py")
